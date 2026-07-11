{{
  config(
    materialized='table'
  )
}}

-- Gold: average, min, max temperature per device across all history.
select
    device_id,
    count(*) as reading_count,
    round(avg(temperature), 2) as avg_temperature,
    min(temperature) as min_temperature,
    max(temperature) as max_temperature
from {{ ref('iot_events_clean') }}
where temperature is not null
group by device_id
