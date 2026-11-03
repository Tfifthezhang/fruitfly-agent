"""Defer lifecycle facts until activation without altering rejected history."""
import logging
from pathlib import Path
from uuid import uuid4

from fruitfly_agent.core.observation import ObservationSink, OperationEvent
from fruitfly_agent.core.session import Session
from fruitfly_agent.core.session.observations import session_observer


logger = logging.getLogger(__name__)


class LifecycleObservations:
    def __init__(self, session: Session, directory: Path) -> None:
        self.session = session
        self.directory = Path(directory)
        self.pending: list[OperationEvent] = []
        self.active = False
        self.closed = False
        self.diagnostic_path = self.directory / (uuid4().hex + '.jsonl')

    def emit(self, event: OperationEvent) -> None:
        if self.closed:
            return
        if self.active:
            session_observer(self.session)(event)
        else:
            self.pending.append(event)
            if len(self.pending) >= 1024:
                self._archive()

    def activate(self) -> None:
        self.active = True
        emit = session_observer(self.session)
        for event in self.pending:
            emit(event)
        self.pending.clear()

    def before_run(self, observer: ObservationSink | None) -> ObservationSink:
        def emit(event: OperationEvent) -> None:
            if not self.active:
                self.activate()
            if observer is not None:
                observer(event)
        return emit

    def _archive(self) -> None:
        if not self.pending:
            return
        try:
            with Session(self.diagnostic_path) as target:
                emit = session_observer(target)
                for event in self.pending:
                    emit(event)
        except Exception:
            logger.warning('lifecycle observation archive unavailable')
        finally:
            self.pending.clear()

    def close(self) -> None:
        # Idle recovery and rejected startup leave the target byte-for-byte intact.
        self._archive()
        self.closed = True
