#!/bin/bash
set -e
source ~/a2a-env.sh
cd ~/a2a-mcp-demo/frontend

VITE_API_URL="$API_URL" npm run build
rm -f site.zip && (cd dist && zip -qr ../site.zip .)

if [ -z "$AMPLIFY_APP_ID" ]; then
  AMPLIFY_APP_ID=$(aws amplify create-app --name a2a-chatbot --query app.appId --output text)
  aws amplify create-branch --app-id "$AMPLIFY_APP_ID" --branch-name main > /dev/null
  echo "export AMPLIFY_APP_ID=\"$AMPLIFY_APP_ID\"" >> ~/a2a-env.sh
fi

D=$(aws amplify create-deployment --app-id "$AMPLIFY_APP_ID" --branch-name main)
JOB_ID=$(echo "$D" | python3 -c 'import sys,json; print(json.load(sys.stdin)["jobId"])')
ZIP_URL=$(echo "$D" | python3 -c 'import sys,json; print(json.load(sys.stdin)["zipUploadUrl"])')
curl -s -X PUT -H "Content-Type: application/zip" --upload-file site.zip "$ZIP_URL"
aws amplify start-deployment --app-id "$AMPLIFY_APP_ID" --branch-name main --job-id "$JOB_ID" > /dev/null

echo "Deploying..."
for i in $(seq 1 24); do
  S=$(aws amplify get-job --app-id "$AMPLIFY_APP_ID" --branch-name main --job-id "$JOB_ID" \
      --query job.summary.status --output text)
  echo "  $S"
  if [ "$S" = "SUCCEED" ] || [ "$S" = "FAILED" ]; then break; fi
  sleep 5
done
echo "Chatbot: https://main.$AMPLIFY_APP_ID.amplifyapp.com"
