from django.db import migrations

# The audit log must stay append-only even for a client that bypasses the ORM.
# UPDATE is never allowed. DELETE is allowed only inside a transaction that has
# explicitly switched on `crm.audit_cleanup` — the hook for the authorised manual
# cleanup procedure of Q14, which does not exist yet.
# TRUNCATE is not covered by a row trigger: it is prevented by database privileges
# once the runtime role is separated from the schema owner (S8).
CREATE = """
CREATE FUNCTION audit_event_append_only() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('crm.audit_cleanup', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'audit_event is append-only: % is not allowed', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_event_append_only
    BEFORE UPDATE OR DELETE ON audit_event
    FOR EACH ROW EXECUTE FUNCTION audit_event_append_only();
"""

DROP = """
DROP TRIGGER audit_event_append_only ON audit_event;
DROP FUNCTION audit_event_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [migrations.RunSQL(CREATE, reverse_sql=DROP)]
