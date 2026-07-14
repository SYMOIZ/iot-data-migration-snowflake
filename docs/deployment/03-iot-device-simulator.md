# 03 · AWS IoT Device Simulator

**Stack:** `IotHackathon-DeviceSimulator` · **Purpose:** generate realistic
wearable telemetry and publish it to the `iot-events` MQTT topic.

This uses the official AWS Solutions **IoT Device Simulator (SO0041)**,
deployed from a lightly patched CloudFormation template, then configured
through its own web console.

---

## Step 1 — Deploy the simulator (CloudFormation)

The stock template pins its Lambda functions to `nodejs18.x`, which AWS no
longer allows for *new* functions. The repo includes a patched template with
the three functions bumped to `nodejs20.x` and nothing else changed.

**Template:** `infra/device-simulator/iot-device-simulator-patched.template`

### Console steps

1. **CloudFormation → Create stack → With new resources.**
2. **Upload a template file** → choose
   `infra/device-simulator/iot-device-simulator-patched.template`.
   (The template exceeds the inline size limit, so the console uploads it to an
   S3 staging bucket automatically.)
3. Stack name: `IotHackathon-DeviceSimulator`.
4. Parameter **UserEmail** → `<YOUR_ADMIN_EMAIL>` (Cognito emails the console
   invite + temporary password here).
5. Acknowledge **CAPABILITY_IAM** and **CAPABILITY_AUTO_EXPAND**, then create.

> **Issue & fix — `nodejs18.x` rejected.** The unmodified AWS template fails
> mid‑create because AWS blocked new `nodejs18.x` Lambda functions on
> 2025‑10‑01. The patched template changes only the three
> `AWS::Lambda::Function` `Runtime` values to `nodejs20.x`. See
> `infra/device-simulator/README.md`.

When the stack reaches **CREATE_COMPLETE**, open its **Outputs** tab and note
the **console URL** (a CloudFront address). Keep this URL private.

---

## Step 2 — Sign in to the simulator console

1. Check `<YOUR_ADMIN_EMAIL>` for the Cognito invitation with a temporary
   password.
2. Open the console URL from the stack Outputs and sign in; set a permanent
   password when prompted.

---

## Step 3 — Create the device type

In the simulator console: **Device Types → Add Device Type**. Configure a
`WearableSensor` type whose payload **exactly matches the pipeline schema**
below. Getting the field names and the topic right here is critical — the
downstream Lambda bridge reads these exact keys.

| Attribute | Type | Settings |
|---|---|---|
| `device_id` | ID / string | length 12, **Static = ON** |
| `timestamp` | Timestamp | default format |
| `latitude` | Float (decimal) | range e.g. `24.85`–`24.87` |
| `longitude` | Float (decimal) | range e.g. `66.99`–`67.01` |
| `temperature` | Float | range `20`–`40` |
| `humidity` | Int | range `30`–`90` |
| `heart_rate` | Int | range `60`–`120` |
| `battery` | Int | range `20`–`100` |

**MQTT topic:** `iot-events`

> **Issue & fix — misconfigured device type (silent no‑data).** Two mistakes
> here stop data cold, with no error anywhere:
> 1. Putting descriptive text (instead of `iot-events`) in the **topic** field
>    — messages publish to a topic the IoT Rule never matches.
> 2. Field names that don't match the pipeline (`Humidity`, `heartrate`,
>    `Battery`, or a nested `location` object) — the Lambda bridge can't read
>    them.
> 3. `device_id` left non‑static — a new random id every message makes every
>    reading look like a new device.
>
> Use the exact field names and topic above, and set `device_id` static. See
> [operations/troubleshooting.md](../operations/troubleshooting.md).

---

## Step 4 — Create and start a simulation

**Simulations → Add Simulation.**

| Field | Value |
|---|---|
| Name | `WearableDemo` |
| Device type | `WearableSensor` |
| Number of devices | `5` |
| Data transmission interval | `10` seconds |
| Duration | as desired |

Save, then **Start** the simulation.

---

## Verification

- In the simulator console the simulation shows **Running** with 5 devices.
- In **AWS IoT Core → MQTT test client**, subscribe to `iot-events` — you
  should see messages from all five devices at the configured interval, each
  carrying the eight fields above with a **stable** `device_id`.

(The IoT Rule and downstream routing are configured in the next step.)

---

Next: [04 · AWS IoT Core](./04-iot-core.md)
