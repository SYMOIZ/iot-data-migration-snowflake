{{
  config(
    materialized='view'
  )
}}

-- Gold: row-level CDC event feed for the Operations dashboard and the Raw
-- Data Explorer. The only Gold model exposed at event granularity (rather
-- than pre-aggregated) - added so the Streamlit dashboard, which is only
-- permitted to query Gold, has something to read for "latest CDC events" /
-- raw event search without touching Bronze or Silver directly.
select
    event_id,
    device_id,
    operation,
    event_timestamp,
    temperature,
    humidity,
    heart_rate,
    battery,
    kafka_offset,
    kafka_create_time
from {{ ref('stg_iot_events') }}
order by kafka_offset desc
