{{
  config(
    materialized='table'
  )
}}

-- Gold: fleet-wide battery health, based on each device's latest reading.
select
    battery_status,
    count(*) as device_count,
    round(avg(battery), 2) as avg_battery
from {{ ref('gold_latest_device_status') }}
group by battery_status
