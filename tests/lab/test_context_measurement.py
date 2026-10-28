"""Precision, multimodal accounting, calibration and cancellation, offline."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace as NS
import unittest

from fruitfly_agent.core.context.budget import InputMeasurement
from fruitfly_agent.core.data_model import ProviderView, UserMessage, ToolResultMessage, ImageBlock, Usage
from fruitfly_agent.core.errors import FatalError
from fruitfly_agent.lab.context_manager.measurement.budget import MeasurementService, MeasurementConfig
from tests.support.loop import make_tool


def view(messages=None, tools=()):
    return ProviderView('fixed prompt', messages or [UserMessage('task')], list(tools), 'fake', 100)


class ContextMeasurementTests(unittest.IsolatedAsyncioTestCase):
    def test_budget_uses_input_plus_effective_output_plus_separate_margin(self):
        measure = InputMeasurement(100, 'fake', 'heuristic', 'request', 50, 10, ('framing',))
        self.assertTrue(measure.fits(160)); self.assertFalse(measure.fits(159))
        self.assertFalse(InputMeasurement(None, 'unavailable', 'unknown', 'request', 0).fits(1000))
        with self.assertRaises(ValueError): InputMeasurement(1, 'fake', 'exact', 'r', 1, uncertain=('image',))

    async def test_tool_result_images_framing_visible_schemas_and_limits_are_counted(self):
        service = MeasurementService()
        provider = NS(effective_output_limit=lambda v: min(v.max_tokens, 32))
        image = ImageBlock('unused-offline-bytes', 'image/png')
        user = await service.measure(view([UserMessage([image])]), provider)
        tool = await service.measure(view([ToolResultMessage('call', [image])]), provider)
        self.assertEqual(user.input_tokens, tool.input_tokens)
        self.assertGreater(tool.input_tokens, 1000)
        self.assertEqual(32, tool.output_reserve)
        self.assertIn('image-estimate', tool.uncertain)
        declared, _ = make_tool()
        plain = service.estimate(view()); visible = service.estimate(view(tools=(declared,)))
        hidden = service.estimate(view(tools=(replace(declared, hide_from_model=True),)))
        self.assertGreater(visible, plain); self.assertEqual(plain, hidden)
        self.assertGreater((await service.measure(view(), provider)).margin, 0)

    async def test_calibration_uses_provider_accounting_and_remains_heuristic(self):
        provider = NS(context_usage_tokens=lambda usage: usage.input_tokens + usage.cache_read_tokens + usage.cache_creation_tokens)
        service = MeasurementService(MeasurementConfig(calibration_samples=2))
        original = await service.measure(view(), provider)
        raw = original.input_tokens
        service.observe(original, Usage(input_tokens=raw, cache_read_tokens=raw, cache_creation_tokens=raw), provider)
        calibrated = await service.measure(view(), provider)
        self.assertGreaterEqual(calibrated.input_tokens, raw * 3)
        self.assertEqual('heuristic', calibrated.quality)
        self.assertEqual(raw, (await service.measure(replace(view(), model='different'), provider)).input_tokens)
        service.observe(calibrated, None, provider)
        self.assertEqual('heuristic', calibrated.quality)
        for i in range(400): await service.measure(replace(view(), model=str(i)), provider)
        self.assertLessEqual(len(service.raw), 256)

    async def test_count_failure_fallback_and_strict_admission_are_distinct(self):
        async def failing(*a, **k): raise ValueError('offline failure')
        provider = NS(input_count_supported=True, count_input=failing)
        result = await MeasurementService(MeasurementConfig(provider_count=True)).measure(view(), provider)
        self.assertEqual('heuristic', result.quality)
        strict = MeasurementService(MeasurementConfig(provider_count=True, strict=True))
        with self.assertRaises(FatalError): await strict.measure(view(), provider)
        with self.assertRaises(ValueError): strict.validate_provider(NS())
        with self.assertRaises(FatalError): await strict.measure(view(), NS())
        with self.assertRaises(ValueError): MeasurementConfig(strict=True)

    async def test_counter_timeout_and_user_cancellation_stop_work(self):
        stopped = asyncio.Event()
        async def waiting(*args, **kwargs):
            try: await asyncio.Event().wait()
            finally: stopped.set()
        provider = NS(input_count_supported=True, count_input=waiting)
        service = MeasurementService(MeasurementConfig(provider_count=True, count_timeout_seconds=.01))
        self.assertEqual('heuristic', (await service.measure(view(), provider)).quality)
        self.assertTrue(stopped.is_set())
        stopped.clear(); signal = asyncio.Event()
        task = asyncio.create_task(service.measure(view(), provider, signal=signal))
        await asyncio.sleep(0); signal.set()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertTrue(stopped.is_set())

    async def test_exact_cache_requires_provider_request_identity(self):
        calls = []
        async def count(v, **kwargs): calls.append(v); return 123
        provider = NS(input_count_supported=True, count_input=count, options='first')
        provider.input_count_identity = lambda v: provider.options
        service = MeasurementService(MeasurementConfig(provider_count=True))
        self.assertEqual('exact', (await service.measure(view(), provider)).quality)
        await service.measure(view(), provider)
        self.assertEqual(1, len(calls))
        provider.options = 'changed'
        await service.measure(view(), provider)
        self.assertEqual(2, len(calls))
        del provider.input_count_identity
        await service.measure(view(), provider); await service.measure(view(), provider)
        self.assertEqual(4, len(calls))

    async def test_auxiliary_request_uses_same_counter_and_rejects_oversized_wire_input(self):
        from fruitfly_agent.lab.context_manager.reduction.inference import AuxiliaryText
        from fruitfly_agent.core.data_model import ContextSnapshot
        from tests.support.faux_provider import FauxProvider
        provider = FauxProvider()
        async def count(*args, **kwargs): return 1000
        provider.input_count_supported = True; provider.count_input = count
        meter = MeasurementService(MeasurementConfig(provider_count=True, strict=True))
        aux = AuxiliaryText(provider, context_window=256, meter=meter)
        snapshot = ContextSnapshot((), (), '', (), 256, 'fake', 32, 'budget')
        result = await aux.request(snapshot, system='system', prompt='short public input', max_tokens=32,
            timeout=1, attempts=1, estimate=lambda text: 1)
        self.assertIsNone(result)
        self.assertEqual([], provider.calls)

    async def test_changed_provider_options_reset_calibration_and_request_identity(self):
        provider = NS(options='first', context_usage_tokens=lambda usage: usage.input_tokens)
        provider.input_measurement_scope = lambda: provider.options
        meter = MeasurementService()
        first = await meter.measure(view(), provider)
        meter.observe(first, Usage(input_tokens=first.input_tokens * 4), provider)
        second = await meter.measure(view(), provider)
        self.assertGreaterEqual(second.input_tokens, first.input_tokens * 4)
        provider.options = 'changed encoding policy'
        reset = await meter.measure(view(), provider)
        self.assertEqual(first.input_tokens, reset.input_tokens)
        self.assertNotEqual(first.request_id, reset.request_id)
