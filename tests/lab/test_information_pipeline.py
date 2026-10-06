"""Read-only multi-Space retrieval, isolation, ranking, and budgeting."""

from __future__ import annotations

import unittest

from fruitfly_agent.lab.context_manager.augmentation.information import (
    BudgetedPostProcessor,
    CallbackInformationRetriever,
    InformationArtifact,
    InformationDescriptor,
    InformationPipeline,
    InformationQuery,
    InformationRef,
    InformationSpace,
    InformationSpaceCatalog,
    InformationSpaceDescriptor,
    TextInformationApplicator,
    create_static_lexical_space,
)


def _artifact(space: str, artifact_id: str, text: str, **kwargs) -> InformationArtifact:
    return InformationArtifact(InformationRef(space, artifact_id), text, **kwargs)


def _pipeline(catalog: InformationSpaceCatalog, *, target: str = "system_prompt") -> InformationPipeline:
    return InformationPipeline(
        InformationDescriptor(
            "lexical-test",
            source_types=frozenset({"external", "cross_trial"}),
            capabilities=frozenset({"retrieve", "read"}),
        ),
        catalog,
        BudgetedPostProcessor(),
        TextInformationApplicator(target=target),
    )


class InformationPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_multi_space_ranking_is_stable_and_preserves_provenance(self) -> None:
        project = create_static_lexical_space(
            "project",
            [
                _artifact("project", "b", "Python testing guide"),
                _artifact("project", "a", "Python testing reference"),
            ],
        )
        docs = create_static_lexical_space(
            "docs",
            [_artifact("docs", "one", "Python provider documentation")],
        )
        result = await _pipeline(InformationSpaceCatalog([project, docs])).select(
            InformationQuery("Python", top_k=3)
        )

        refs = [hit.artifact.ref for hit in result.hits]
        self.assertEqual(
            [
                InformationRef("docs", "one"),
                InformationRef("project", "a"),
                InformationRef("project", "b"),
            ],
            refs,
        )

    async def test_scope_and_explicit_space_filter_are_enforced(self) -> None:
        workspace = create_static_lexical_space(
            "workspace-docs", [_artifact("workspace-docs", "a", "alpha")], scope="workspace"
        )
        user = create_static_lexical_space(
            "user-docs", [_artifact("user-docs", "a", "alpha")], scope="user"
        )
        pipeline = _pipeline(InformationSpaceCatalog([workspace, user]))

        result = await pipeline.select(
            InformationQuery("alpha", scope="user", space_ids=("user-docs",))
        )
        self.assertEqual([InformationRef("user-docs", "a")], [h.artifact.ref for h in result.hits])

    async def test_sensitive_artifacts_are_filtered_by_default(self) -> None:
        space = create_static_lexical_space(
            "project",
            [
                _artifact("project", "public", "alpha public"),
                _artifact("project", "secret", "alpha secret", sensitive=True),
            ],
        )
        result = await _pipeline(InformationSpaceCatalog([space])).select(InformationQuery("alpha"))
        self.assertEqual([InformationRef("project", "public")], [h.artifact.ref for h in result.hits])

    async def test_one_broken_space_does_not_block_other_spaces(self) -> None:
        async def broken(query):
            raise RuntimeError("offline")

        broken_space = InformationSpace(
            InformationSpaceDescriptor("broken"),
            retriever=CallbackInformationRetriever("broken", broken),
        )
        healthy = create_static_lexical_space(
            "healthy", [_artifact("healthy", "a", "alpha")]
        )
        result = await _pipeline(InformationSpaceCatalog([broken_space, healthy])).select(
            InformationQuery("alpha")
        )

        self.assertEqual([InformationRef("healthy", "a")], [h.artifact.ref for h in result.hits])
        self.assertEqual("broken", result.errors[0].space_id)
        self.assertIn("RuntimeError", result.errors[0].message)

    async def test_get_reads_exact_artifact(self) -> None:
        space = create_static_lexical_space("docs", [_artifact("docs", "a", "alpha")])
        catalog = InformationSpaceCatalog([space])
        artifact = await catalog.get(InformationRef("docs", "a"))
        self.assertEqual("alpha", artifact.text)

    def test_duplicate_space_is_rejected(self) -> None:
        space = create_static_lexical_space("docs", [])
        with self.assertRaisesRegex(ValueError, "duplicate information space"):
            InformationSpaceCatalog([space, space])


if __name__ == "__main__":
    unittest.main()
