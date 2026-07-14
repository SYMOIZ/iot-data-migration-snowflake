{{
  config(
    materialized='table'
  )
}}

-- Gold: most recent reading per device, for a live fleet-status view.
with ranked as (
    select
        *,
        row_number() over (
            partition by device_id
            order by "timestamp" desc
        ) as rn
    from {{ ref('iot_events_clean') }}
)

select
    device_id,
    "timestamp" as last_seen_at,
    latitude,
    longitude,
    temperature,
    humidity,
    heart_rate,
    battery,
    case
        when battery < 20 then 'low'
        when battery < 50 then 'medium'
        else 'ok'
    end as battery_status
from ranked
where rn = 1
