# Pipecat audio recording S3 multipart upload example

This is a simple Pipecat bot example for how to save audio recordings to s3. It accounts for long audio recordings (multipart) as well as short audio recordings.

To record Pipecat audio, a pipeline should use `AudioBufferProcessor`. By default, all user and bot audio is kept in a buffer in memory until the end of the call.  If the conversation is long, this buffer will grow very large and can cause an OOM (out of memory) error.  To avoid this, one can pass in the param [buffer-size](https://docs.pipecat.ai/server/utilities/audio/audio-buffer-processor#param-buffer-size) to trigger the event handler when the buffer reaches this size.  This limits memory use for the audio buffer to the `buffer-size` and thus helps avoid OOM errors.

This example code illustrates how to implement `AudioBufferProcessor` with a 5mb buffer-size and event handlers to upload audio to an AWS s3 bucket.

## Prerequisites

- [Pipecat basics (Quickstart)](https://github.com/pipecat-ai/pipecat/tree/main/examples/quickstart)
- [`AudioBufferProcessor` basics](https://github.com/pipecat-ai/pipecat/blob/main/examples/foundational/34-audio-recording.py)
- AWS account

## Create AWS resources

1. Login to AWS CLI

```bash
AWS_PROFILE=YOUR_AWS_PROFILE aws sso login
```

2. Create S3 Bucket

```bash
AWS_PROFILE=YOUR_AWS_PROFILE \
aws s3api create-bucket \
--bucket YOUR_BUCKET_NAME \
--region YOUR_REGION
```

3. Create IAM policies and role
```bash
AWS_PROFILE=YOUR_AWS_PROFILE \
./create_s3_role.sh YOUR_BUCKET_NAME
```

## Setup bot

1. Install dependencies:

   ```bash
   uv sync
   ```

2. Configure your API keys:

   Create a `.env` file:

   ```bash
   cp env.example .env
   ```

   Then, add your API keys:

   ```ini
   CARTESIA_API_KEY=your_cartesia_api_key
   DEEPGRAM_API_KEY=your_deepgram_api_key
   GOOGLE_API_KEY=your_google_api_key
   ```

   As well as your AWS resources:

   ```ini
   AWS_ACCESS_KEY_ID=...
   AWS_SECRET_ACCESS_KEY=...
   AWS_ROLE_ARN=arn:aws:iam::YOUR_ACCOUNT:role/PipecatS3Upload
   AWS_BUCKET_NAME=your_bucket_name
   AWS_DEFAULT_REGION=your_region
   ```

## Run bot

   ```bash
   uv run python bot.py
   ```

> To trigger the 5mb audio buffer-size handler, talk to the bot for at least 1.5 - 2 minutes.

After the pipeline finishes, which happens when the bot leaves the call, ie if `terminate_call` function is triggered or when the pipeline idle times out, the `@audio_buffer.event_handler`s will run and finish the multipart upload. Check `YOUR_BUCKET_NAME` in AWS s3 dashboard. 

By default, the audio files will save to the following s3keys:
```ini
s3://YOUR_BUCKET_NAME/000000000000_test_conversations/CONVERSATION_UUID/CONVERSATION_UUID.wav
s3://YOUR_BUCKET_NAME/000000000000_test_conversations/CONVERSATION_UUID/CONVERSATION_UUID_bot.wav
s3://YOUR_BUCKET_NAME/000000000000_test_conversations/CONVERSATION_UUID/CONVERSATION_UUID_user.wav
```
update this s3key [here]().

## Deploy bot

See [quickstart README](https://github.com/pipecat-ai/pipecat/blob/main/examples/quickstart/README.md#step-2-deploy-to-production-5-min).

## Pro Tip
Check for and abort dangling multipart uploads (they cost $$$).  They can build up, usually during development.

```bash
AWS_PROFILE=YOUR_AWS_PROFILE \
aws s3api list-multipart-uploads \
--bucket <YOUR_BUCKET_NAME>
```

To abort any dangling multipart uploads, you need the s3 key and upload-id. Abort like so:
```bash
AWS_PROFILE=YOUR_AWS_PROFILE \
aws s3api abort-multipart-upload \
--bucket <YOUR_BUCKET_NAME> \
 --key "fe6c9ee9-220b-4dbe-aea0-9f42dc979d43/fe6c9ee9-220b-4dbe-aea0-9f42dc979d43.wav" \
 --upload-id "6dZUbxSxlEA4SUq73rD8V7uEq3Mc0eDTtXrFwknuFnKhMopfLni5RHRKyK7qnTMf2KlzMMX6eEJBTuK73fRSO7S55DXFw8.fmWMFIdBh1NLsMJ_bvrRtXq_.xU4jc8CQ"
```