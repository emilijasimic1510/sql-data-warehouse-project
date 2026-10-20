"""Read-only source verification and opt-in mart-only transactional integration tests."""
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from crm_incremental.verification import business_snapshot
from mart_pipeline import runner
from mart_pipeline.deploy import deploy
from warehouse_pipeline.connection import Settings,connect,check_target

pytestmark=pytest.mark.skipif(os.getenv('DW_RUN_MART_INTEGRATION')!='1',reason='Opt-in mart SQL tests')
ROOT=Path(__file__).resolve().parents[2]


def fingerprint(cursor,name,exclude_first=False):
 rows=cursor.execute('SELECT * FROM '+name).fetchall()
 encoded=sorted(json.dumps(list(x)[1:] if exclude_first else list(x),default=str,separators=(',',':'),ensure_ascii=False).encode() for x in rows)
 h=hashlib.sha256()
 for x in encoded:h.update(len(x).to_bytes(8,'big'));h.update(x)
 return dict(rows=len(rows),sha256=h.hexdigest())


def key_maps(cursor):
 return dict(customer=[list(x) for x in cursor.execute('SELECT customer_id,customer_key FROM mart.dim_customer ORDER BY customer_key').fetchall()],
             product=[list(x) for x in cursor.execute('SELECT product_number,valid_from,product_key FROM mart.dim_product ORDER BY product_key').fetchall()],
             date=[list(x) for x in cursor.execute('SELECT calendar_date,date_key FROM mart.dim_date ORDER BY date_key').fetchall()])


@pytest.fixture(scope='module')
def db(request):
 s=Settings(r'DESKTOP-N1402MQ\SQLEXPRESS','DataWarehouse',ROOT/'datasets','',expected_server=r'DESKTOP-N1402MQ\SQLEXPRESS',trust_server_certificate=True)
 c=connect(s);u=c.cursor();assert check_target(u,s,require_procedures=False)==(s.expected_server,s.database)
 evidence={'runs':[],'checks':{}}
 yield s,u,evidence
 try:
  before=json.loads((ROOT/'reports/phase4a-business-before.json').read_text())
  after=business_snapshot(u)
  for name in ('customers','staging','batches','events','attempts'):after['crm_incremental.'+name]=fingerprint(u,'crm_incremental.'+name)
  assert before==after,'Original business/demo objects changed'
  evidence['protected_objects_unchanged']=True
  evidence['pytest_failures_at_teardown']=request.session.testsfailed
  p=ROOT/'reports'/f'phase4a-sql-evidence-{uuid4()}.json';p.write_text(json.dumps(evidence,indent=2,default=str),encoding='utf-8')
  print('Evidence:',p)
 finally:u.close();c.close()


def test_01_two_loads_stable_dimensions_and_full_fact_multiset(db):
 s,u,e=db
 first=runner.run(s,execute=True,report_path=ROOT/'reports'/f'phase4a-first-load-{uuid4()}.json')
 assert first['status']=='PASS',first
 assert all(q['anomaly_count']==0 for q in first['checks'] if q['severity']=='ERROR')
 dimensions={t:fingerprint(u,'mart.'+t) for t in ('dim_customer','dim_product','dim_date')}
 maps=key_maps(u); facts=fingerprint(u,'mart.fact_sales',True)
 second=runner.run(s,execute=True,report_path=ROOT/'reports'/f'phase4a-second-load-{uuid4()}.json')
 assert second['status']=='PASS',second
 assert maps==key_maps(u),'Persistent dimension keys changed'
 assert dimensions=={t:fingerprint(u,'mart.'+t) for t in dimensions},'Dimension attributes changed'
 assert facts==fingerprint(u,'mart.fact_sales',True),'Full fact multiset changed'
 e['runs']=[first,second];e['dimensions']=dimensions;e['fact_business_multiset']=facts
 e['dimension_key_map_sha256']=hashlib.sha256(json.dumps(maps,default=str,sort_keys=True).encode()).hexdigest()
 e['checks']['keys_and_complete_fact_multiset_stable']=True
 # Customer and current product attributes agree with Gold, regardless of their different surrogate keys.
 difference=u.execute('''SELECT COUNT_BIG(*) FROM (
  SELECT customer_id,customer_number,first_name,last_name,country,marital_status,gender,birthdate,create_date
   FROM mart.dim_customer WHERE is_in_source=1
  EXCEPT SELECT customer_id,customer_number,first_name,last_name,country,marital_status,gender,birthdate,create_date FROM gold.dim_customers) x''').fetchone()[0]
 assert difference==0
 difference=u.execute('''SELECT COUNT_BIG(*) FROM (
  SELECT source_product_id,product_number,product_name,category_id,category,subcategory,maintenance,CAST(cost AS int) AS cost,product_line,valid_from
   FROM mart.dim_product WHERE is_current=1
  EXCEPT SELECT product_id,product_number,product_name,category_id,category,subcategory,maintenance,cost,product_line,start_date FROM gold.dim_products) x''').fetchone()[0]
 assert difference==0
 e['checks']['customer_and_current_product_attributes_match_gold']=True


def test_02_actual_interval_boundaries_and_missing_dates(db):
 _,u,e=db
 for name,sql in (
 ('start',"SELECT COUNT_BIG(*) FROM mart.fact_sales f JOIN mart.dim_product p ON f.product_key=p.product_key WHERE p.product_key>0 AND f.source_order_date=p.valid_from"),
 ('end',"SELECT COUNT_BIG(*) FROM mart.fact_sales f JOIN mart.dim_product p ON f.product_key=p.product_key WHERE p.product_key>0 AND f.source_order_date=p.valid_to")):
  count=u.execute(sql).fetchone()[0]
  assert count==(155 if name=='start' else 25)
  e['checks'][name+'_boundary_sales']=count
 # Test each observed product interval at start/end, adjacent day, and NULL order date against SOURCE history.
 difference=u.execute('''WITH test_dates AS(
  SELECT product_number,valid_from test_date FROM mart.dim_product WHERE is_in_source=1
  UNION ALL SELECT product_number,valid_to FROM mart.dim_product WHERE is_in_source=1 AND valid_to IS NOT NULL
  UNION ALL SELECT product_number,DATEADD(day,-1,valid_from) FROM mart.dim_product WHERE is_in_source=1
  UNION ALL SELECT product_number,DATEADD(day,1,valid_to) FROM mart.dim_product WHERE is_in_source=1 AND valid_to IS NOT NULL
  UNION ALL SELECT product_number,CAST(NULL AS date) FROM mart.dim_product WHERE is_in_source=1)
 SELECT COUNT_BIG(*) FROM test_dates t
 OUTER APPLY(SELECT COUNT_BIG(*) n,MIN(source_product_id) id FROM mart.dim_product p WHERE p.is_in_source=1
  AND p.product_number=t.product_number AND t.test_date>=p.valid_from AND (p.valid_to IS NULL OR t.test_date<=p.valid_to)) m
 OUTER APPLY(SELECT COUNT_BIG(*) n,MIN(prd_id) id FROM silver.crm_product_info p WHERE p.prd_key=t.product_number
  AND t.test_date>=p.prd_start_dt AND (p.prd_end_dt IS NULL OR t.test_date<=p.prd_end_dt)) s
 WHERE m.n<>s.n OR m.n>1 OR COALESCE(m.id,-1)<>COALESCE(s.id,-1)''').fetchone()[0]
 assert difference==0
 assert u.execute("SELECT COUNT_BIG(*) FROM mart.fact_sales WHERE source_order_date IS NULL AND (order_date_key<>0 OR product_key<>0 OR product_match_reason<>'MISSING_ORDER_DATE')").fetchone()[0]==0
 e['checks']['all_source_interval_edges_match']=True


def test_03_quality_failure_rolls_back_publication(db,monkeypatch):
 s,u,e=db
 before=fingerprint(u,'mart.fact_sales')
 real_connect=runner.connect; observed={}
 class FaultCursor:
  def __init__(self,raw):self.raw=raw
  def __getattr__(self,n):return getattr(self.raw,n)
  def execute(self,sql,*args):
   if sql=='EXEC mart.check_quality;':
    observed['inside_transaction']=self.raw.execute('SELECT @@TRANCOUNT').fetchone()[0]
    self.raw.execute('UPDATE mart.fact_sales SET quantity=quantity+1 WHERE fact_key=(SELECT MIN(fact_key) FROM mart.fact_sales)')
   return self.raw.execute(sql,*args)
 class FaultConnection:
  def __init__(self,raw):self.raw=raw
  def __getattr__(self,n):return getattr(self.raw,n)
  def cursor(self):return FaultCursor(self.raw.cursor())
 monkeypatch.setattr(runner,'connect',lambda settings:FaultConnection(real_connect(settings)))
 result=runner.run(s,execute=True)
 assert result['status']=='FAIL' and result['committed'] is not True
 assert any(q['check_id']=='M10' and q['anomaly_count']>0 for q in result['checks'])
 assert any(q['check_id']=='M12' and q['anomaly_count']>0 for q in result['checks'])
 assert before==fingerprint(u,'mart.fact_sales'),'Previous committed publication was not restored'
 assert observed['inside_transaction']==1
 e['checks']['real_quality_failure_before_commit_rolled_back']=True


def test_04_redeployment_and_gold_difference(db):
 s,u,e=db
 before={t:fingerprint(u,'mart.'+t) for t in ('dim_customer','dim_product','dim_date','fact_sales')}
 outcome=deploy(s);assert outcome['status']=='VERIFIED'
 assert before=={t:fingerprint(u,'mart.'+t) for t in before}
 metrics={
 'historical_versions':u.execute('SELECT COUNT_BIG(*) FROM mart.dim_product WHERE is_in_source=1 AND is_current=0').fetchone()[0],
 'historical_sales':u.execute('SELECT COUNT_BIG(*) FROM mart.fact_sales f JOIN mart.dim_product p ON p.product_key=f.product_key WHERE p.product_key>0 AND p.is_current=0').fetchone()[0],
 'gold_product_rows':u.execute('SELECT COUNT_BIG(*) FROM gold.dim_products').fetchone()[0],
 'gold_fact_rows':u.execute('SELECT COUNT_BIG(*) FROM gold.fact_sales').fetchone()[0]}
 assert metrics['historical_versions']==102 and metrics['historical_sales']==8246
 unknown=[dict(reason=x[0],rows=x[1]) for x in u.execute('SELECT product_match_reason,COUNT_BIG(*) FROM mart.fact_sales GROUP BY product_match_reason ORDER BY product_match_reason').fetchall()]
 e['gold_comparison']=metrics;e['product_match_reasons']=unknown;e['deployment']=outcome
 e['checks']['redeployment_keeps_all_data']=True
