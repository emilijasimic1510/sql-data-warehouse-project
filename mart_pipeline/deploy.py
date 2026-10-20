"""Explicit transactional deployment; reject both metadata drift and source-version drift."""
import argparse
import hashlib
from pathlib import Path

from warehouse_pipeline.connection import Settings,connect,check_target
from warehouse_pipeline.reporting import PipelineError
from .runner import BEGIN,drain,error_message

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=tuple(ROOT/"scripts/mart"/name for name in ("schema.sql","load.sql","quality.sql"))
SIGNATURE_SQL="""SELECT @signature=CONVERT(varchar(64),HASHBYTES('SHA2_256',CONVERT(nvarchar(max),(
 SELECT o.name,o.type,OBJECT_DEFINITION(o.object_id) AS definition,
  (SELECT c.name,TYPE_NAME(c.user_type_id) AS datatype,c.max_length,c.precision,c.scale,c.is_nullable,
          c.is_identity,c.is_computed,c.collation_name,OBJECT_DEFINITION(c.default_object_id) AS default_definition
   FROM sys.columns c WHERE c.object_id=o.object_id ORDER BY c.column_id FOR XML PATH('column'),TYPE) AS columns,
  (SELECT i.name,i.is_unique,i.is_primary_key,i.is_disabled,i.type,i.filter_definition,
      (SELECT COL_NAME(ic.object_id,ic.column_id) AS column_name,ic.key_ordinal,ic.is_descending_key,ic.is_included_column
       FROM sys.index_columns ic WHERE ic.object_id=i.object_id AND ic.index_id=i.index_id
       ORDER BY ic.index_column_id FOR XML PATH('index_column'),TYPE) AS index_columns
   FROM sys.indexes i WHERE i.object_id=o.object_id ORDER BY i.index_id FOR XML PATH('index'),TYPE) AS indexes,
  (SELECT k.name,k.is_disabled,k.is_not_trusted,k.delete_referential_action,k.update_referential_action,
      (SELECT COL_NAME(f.parent_object_id,f.parent_column_id) AS source_column,
       OBJECT_SCHEMA_NAME(f.referenced_object_id) AS target_schema,OBJECT_NAME(f.referenced_object_id) AS target_table,
       COL_NAME(f.referenced_object_id,f.referenced_column_id) AS target_column
       FROM sys.foreign_key_columns f WHERE f.constraint_object_id=k.object_id
       ORDER BY f.constraint_column_id FOR XML PATH('mapping'),TYPE) AS mappings
   FROM sys.foreign_keys k WHERE k.parent_object_id=o.object_id ORDER BY k.name FOR XML PATH('fk'),TYPE) AS foreign_keys,
  (SELECT ch.name,ch.is_disabled,ch.is_not_trusted,ch.definition FROM sys.check_constraints ch
   WHERE ch.parent_object_id=o.object_id ORDER BY ch.name FOR XML PATH('check'),TYPE) AS checks
 FROM sys.objects o WHERE o.schema_id=SCHEMA_ID(N'mart')
 ORDER BY o.name,o.type FOR XML PATH('object'),TYPE
))),2);"""


def schema_signature(cursor):
    sql="DECLARE @signature varchar(64);\n"+SIGNATURE_SQL+"\nSELECT @signature;"
    return cursor.execute(sql).fetchone()[0]


def property_value(cursor,name):
    row=cursor.execute("SELECT CONVERT(nvarchar(128),value) FROM sys.extended_properties WHERE class=3 AND major_id=SCHEMA_ID(N'mart') AND name=?",name).fetchone()
    return row[0] if row else None


def deploy(settings):
    source_hash=hashlib.sha256(b"\0".join(p.read_bytes() for p in SCRIPTS)).hexdigest()
    connection=connect(settings);cursor=connection.cursor()
    try:
        identity=check_target(cursor,settings,require_procedures=False)
        if identity[1].casefold()!="datawarehouse":
            raise PipelineError("Mart deployment must target DataWarehouse.")
        print(f"Confirmed before deployment: {identity}",flush=True)
        cursor.execute(BEGIN);drain(cursor)
        existing=cursor.execute("SELECT COUNT(*) FROM sys.objects WHERE schema_id=SCHEMA_ID(N'mart')").fetchone()[0]
        if existing:
            signature=schema_signature(cursor)
            if property_value(cursor,"contract_version")!="1" or property_value(cursor,"schema_signature")!=signature or property_value(cursor,"source_signature")!=source_hash:
                raise PipelineError("Incompatible mart schema or deployment scripts; explicit migration required.")
            status="VERIFIED"
        else:
            for script in SCRIPTS:
                cursor.execute(script.read_text(encoding="utf-8-sig"));drain(cursor)
            signature=schema_signature(cursor)
            for name,value in (("contract_version","1"),("schema_signature",signature),("source_signature",source_hash)):
                cursor.execute("EXEC sys.sp_addextendedproperty @name=?,@value=?,@level0type=N'SCHEMA',@level0name=N'mart'",name,value)
                drain(cursor)
            status="CREATED"
        cursor.execute("COMMIT TRANSACTION;");drain(cursor)
        return dict(status=status,schema_signature=signature,source_signature=source_hash)
    except Exception:
        try:
            cursor.execute("IF XACT_STATE()<>0 ROLLBACK TRANSACTION;");drain(cursor)
        except Exception:
            pass
        raise
    finally:
        cursor.close();connection.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description="Explicit non-destructive mart deployment")
    for name in ("server","database","expected-server"):
        parser.add_argument("--"+name,required=True)
    parser.add_argument("--driver",default="ODBC Driver 17 for SQL Server")
    parser.add_argument("--trust-server-certificate",action="store_true")
    args=parser.parse_args(argv)
    settings=Settings(args.server,args.database,ROOT/"datasets","",args.driver,args.expected_server,args.trust_server_certificate)
    try:
        print(deploy(settings))
    except Exception as exc:
        print(error_message(exc));return 1
    return 0


if __name__=="__main__":
    raise SystemExit(main())
