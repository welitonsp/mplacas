# Register all ORM models with Base.metadata so that FK resolution works in any test
# that uses Base.metadata.create_all with an in-memory SQLite engine.
import mplacas.alerts.db_models  # noqa: F401
import mplacas.organizations.db_models  # noqa: F401
import mplacas.audit.db_models  # noqa: F401
import mplacas.billing.db_models  # noqa: F401
import mplacas.climate.db_models  # noqa: F401
import mplacas.collection.db_models  # noqa: F401
import mplacas.credentials.db_models  # noqa: F401
import mplacas.db.models  # noqa: F401
import mplacas.events.db_models  # noqa: F401
import mplacas.operations.models  # noqa: F401
import mplacas.orchestration.db_models  # noqa: F401
import mplacas.reports.db_models  # noqa: F401
