# AWS IoT Device Simulator (Task 1.2)

`iot-device-simulator-patched.template` is the official AWS Solutions "IoT Device
Simulator" (SO0041 v3.0.9) CloudFormation template, downloaded from AWS's
`solutions-reference` S3 bucket, with exactly one change: all three
`AWS::Lambda::Function` resources were bumped from `Runtime: nodejs18.x` to
`Runtime: nodejs20.x`.

## Why

The solution was deprecated by AWS on 2026-01-29 and has not been updated since.
AWS blocked creation of new Lambda functions on `nodejs18.x` starting
2025-10-01, so the unmodified template fails during stack creation. This is
the minimum change needed to deploy it; no other resources or logic were
altered.

## Deploy

```
aws cloudformation create-stack \
  --stack-name IotHackathon-DeviceSimulator \
  --template-body file://iot-device-simulator-patched.template \
  --parameters ParameterKey=UserEmail,ParameterValue=<your-email> \
  --capabilities CAPABILITY_IAM
```

(The original deployment used a presigned S3 URL instead of `--template-body`
because the template exceeds the 51,200-byte inline body limit.)
