FROM apache/airflow:3.3.2-python3.12@sha256:9df9c8be4096b9cc626bd7cb1f2b8c712eef66c59c615f8c7e6200871ca10bd1
USER root
# This pinned official image already includes Microsoft's ODBC 18 driver and repo.
# Verify it instead of adding a conflicting second Signed-By repository definition.
RUN dpkg-query -W -f='${Version}\n' msodbcsql18 | grep -Fx '18.7.1.1-1' \
    && dpkg-query -W libgssapi-krb5-2
USER airflow
RUN pip install --no-cache-dir apache-airflow==3.3.2 apache-airflow-providers-standard==1.19.0 psycopg2-binary==2.9.13 \
    --constraint https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.12.txt
COPY requirements.txt /tmp/project-requirements.txt
# Keep the project's tested pandas pin; the initial Airflow constraint pins 3.0.5.
RUN pip install --no-cache-dir apache-airflow==3.3.2 -r /tmp/project-requirements.txt && pip check
COPY --chown=airflow:root csv_validation /opt/project/app/csv_validation
COPY --chown=airflow:root warehouse_pipeline /opt/project/app/warehouse_pipeline
COPY --chown=airflow:root mart_pipeline /opt/project/app/mart_pipeline
COPY --chown=airflow:root e2e_pipeline /opt/project/app/e2e_pipeline
COPY --chown=airflow:root airflow_orchestration /opt/project/app/airflow_orchestration
COPY --chown=airflow:root orchestration/airflow/dags /opt/airflow/dags
COPY --chown=airflow:root orchestration/airflow/validate_dag.py /opt/project/validate_dag.py
ENV PYTHONPATH=/opt/project/app

