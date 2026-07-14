{{
  config(
    materialized='view'
  )
}}

-- Bronze staging model: parses the VARIANT columns from the raw Debezium CDC
-- envelope into relational columns. Uses COALESCE(after, before) so delete
-- events (op='d', where "after" is null) still produce a usable row from the
-- pre-delete state, instead of a row of nulls.
select
    coalesce(record_content:after:id, record_content:before:id)::number as event_id,
    coalesce(record_content:after:device_id, record_content:before:device_id)::string as device_id,
    coalesce(record_content:after:timestamp, record_content:before:timestamp)::timestamp_ntz as event_timestamp,
    coalesce(record_content:after:latitude, record_content:before:latitude)::float as latitude,
    coalesce(record_content:after:longitude, record_content:before:longitude)::float as longitude,
    coalesce(record_content:after:temperature, record_content:before:temperature)::float as temperature,
    coalesce(record_content:after:humidity, record_content:before:humidity)::float as humidity,
    coalesce(record_content:after:heart_rate, record_content:before:heart_rate)::float as heart_rate,
    coalesce(record_content:after:battery, record_content:before:battery)::float as battery,
    record_content:op::string as operation,
    record_content:ts_ms::number as source_ts_ms,
    record_content:source:lsn::number as source_lsn,
    record_metadata:CreateTime::number as kafka_create_time,
    record_metadata:offset::number as kafka_offset,
    record_metadata:partition::number as kafka_partition
from {{ source('bronze', 'iot_events_raw') }}
