{{
  config(
    materialized='table'
  )
}}

-- Silver: one deduplicated, current-state row per source event_id (keeps the
-- most recent CDC event per id, by Kafka offset/create-time), with basic data
-- quality filters. Delete events are excluded from this current-state view.
with ranked as (
    select
        *,
        row_number() over (
            partition by event_id
            order by kafka_offset desc, kafka_create_time desc
        ) as rn
    from {{ ref('stg_iot_events') }}
    where operation != 'd'
)

select
    event_id,
    device_id,
    event_timestamp as "timestamp",
    latitude,
    longitude,
    temperature,
    humidity,
    heart_rate,
    battery,
    operation
from ranked
where rn = 1
  and device_id is not null
  and event_timestamp is not null
  and latitude between -90 and 90
  and longitude between -180 and 180
  and humidity between 0 and 100
  and battery between 0 and 100
