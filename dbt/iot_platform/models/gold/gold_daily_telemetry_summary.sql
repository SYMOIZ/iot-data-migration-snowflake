{{
  config(
    materialized='table'
  )
}}

-- Gold: fleet-wide telemetry rollup per calendar day.
select
    date_trunc('day', "timestamp") as event_date,
    count(*) as reading_count,
    count(distinct device_id) as active_device_count,
    round(avg(temperature), 2) as avg_temperature,
    round(avg(humidity), 2) as avg_humidity,
    round(avg(heart_rate), 2) as avg_heart_rate,
    round(avg(battery), 2) as avg_battery
from {{ ref('iot_events_clean') }}
group by date_trunc('day', "timestamp")
order by event_date
