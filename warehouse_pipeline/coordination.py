"""Database-scoped session lock shared by warehouse and mart Python writers."""

from .reporting import PipelineError

RESOURCE = "datawarehouse.pipeline.v1"
ACQUIRE = """DECLARE @result int;
EXEC @result=sys.sp_getapplock @Resource=?, @LockMode='Exclusive', @LockOwner='Session',
    @LockTimeout=?, @DbPrincipal='public';
SELECT @result;"""
RELEASE = """DECLARE @result int;
EXEC @result=sys.sp_releaseapplock @Resource=?, @LockOwner='Session', @DbPrincipal='public';
SELECT @result;"""


class ProjectSession:
    """One connection owner; children borrow it and never reacquire/release its lock."""

    def __init__(self, timeout_ms=10000, on_ready=None):
        if type(timeout_ms) is not int or not 0 <= timeout_ms <= 60000:
            raise ValueError("Lock timeout must be an integer from 0 to 60000 ms")
        self.timeout_ms = timeout_ms
        self.on_ready = on_ready
        self.connection = None
        self.target = None
        self.held = False
        self.status = "NOT_ACQUIRED"

    def acquire(self, cursor, target):
        if self.held:
            if target != self.target:
                raise PipelineError("Borrowed session target differs from its lock owner.")
            return
        self.target = target
        result = cursor.execute(ACQUIRE, RESOURCE, self.timeout_ms).fetchone()[0]
        while cursor.nextset():
            pass
        if not isinstance(result, int) or result < 0:
            self.status = "FAILED"
            raise PipelineError("Project writer lock unavailable; no loader started.")
        self.held = True
        self.status = "HELD"
        if self.on_ready is not None:
            self.on_ready(cursor)

    def release(self):
        if not self.held:
            return
        cursor = self.connection.cursor()
        try:
            result = cursor.execute(RELEASE, RESOURCE).fetchone()[0]
            while cursor.nextset():
                pass
            if not isinstance(result, int) or result < 0:
                self.status = "RELEASE_FAILED"
                raise PipelineError("Project writer lock release failed; connection close is the fallback.")
            self.held = False
            self.status = "RELEASED"
        except Exception:
            self.status = "RELEASE_FAILED"
            raise
        finally:
            cursor.close()

    def disconnect(self):
        if self.connection is not None:
            try:
                self.connection.close()
            finally:
                self.connection = None
                self.held = False

    def close(self):
        try:
            self.release()
        finally:
            self.disconnect()
