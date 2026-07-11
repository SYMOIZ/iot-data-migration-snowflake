{{
  config(
    materialized='table'
  )
}}

-- Gold: average, min, max heart rate per device across all history.
select
    device_id,
    count(*) as reading_count,
    round(avg(heart_rate), 2) as avg_heart_rate,
    min(heart_rate) as min_heart_rate,
    max(heart_rate) as max_heart_rate
from {{ ref('iot_events_clean') }}
where heart_rate is not null
group by device_id
