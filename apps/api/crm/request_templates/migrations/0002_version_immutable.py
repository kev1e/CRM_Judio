from django.db import migrations

# D009: a published version never changes. Enforced in the database as well, so
# that no code path, script or manual query can rewrite a form that requests
# were made with.
CREATE = """
CREATE FUNCTION request_templates_version_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'request_templates_version is immutable';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER request_templates_version_immutable
BEFORE UPDATE OR DELETE ON request_templates_version
FOR EACH ROW EXECUTE FUNCTION request_templates_version_immutable();
"""

DROP = """
DROP TRIGGER request_templates_version_immutable ON request_templates_version;
DROP FUNCTION request_templates_version_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [("request_templates", "0001_initial")]

    operations = [migrations.RunSQL(CREATE, reverse_sql=DROP)]
