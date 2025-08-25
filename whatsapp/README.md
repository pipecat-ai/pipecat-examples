
- https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/
- https://developers.facebook.com/docs/whatsapp/cloud-api/calling/user-initiated-calls

- IMPORTANT:
  - Need to enable to accept the "call" in the test phone number


```
filipifuchter@Filipis-MacBook-Pro recovery-codes % curl -i -X POST \
  https://graph.facebook.com/v23.0/703312242875221/messages \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{ "messaging_product": "whatsapp", "to": "+5548988331173", "type": "template", "template": { "name": "hello_world", "language": { "code": "en_US" } } }'
```


https://developers.facebook.com/docs/whatsapp/cloud-api/calling/reference#sdp-overview-and-sample-sdp-structures

curl -i -X POST 'https://graph.facebook.com/v14.0/1234567890/calls' \
-H 'Content-Type: application/json' \
-H 'Authorization: Bearer EAADUMAze4GIBO1B7B.....<REPLACE_WITH_YOUR_TOKEN>' \
-d '{
 "messaging_product": "whatsapp",
 "to": "14085550000",
 "action": "accept",
 "call_id": "wacid.HBgLMTY1MDMxMzM5NzQVAgASGCA5ODkyMDk2RkM2NUM1QTYwRkM4NjFDQzk0NkQwNDBCRRwYCzEyMjQ1NTU0NDg5FQIAAA==",
 "session": {
     "sdp": "v=0\r\no=- 7669997803033704573 2 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\na=group:BUNDLE 0\r\na=extmap-allow-mixed\r\na=msid-semantic: WMS 3c28addc-03b7-4170-b5cd-535bfe767e75\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111 63 9 0 8 110 126\r\nc=IN IP4 0.0.0.0\r\na=rtcp:9 IN IP4 0.0.0.0\r\na=ice-ufrag:6O0H\r\na=ice-pwd:TYCbtfOrBMPpfxFRgSbYnuTI\r\na=ice-options:trickle\r\na=fingerprint:sha-256 9F:45:2C:A8:C3:C0:CC:9B:59:4F:D1:02:56:52:FA:36:00:BE:C0:79:87:B3:D9:9C:3E:BF:60:98:25:B4:26:FC\r\na=setup:active\r\na=mid:0\r\na=extmap:1 urn:ietf:params:rtp-hdrext:ssrc-audio-level\r\na=extmap:2 http://www.webrtc.org/experiments/rtp-hdrext/abs-send-time\r\na=extmap:3 http://www.ietf.org/id/draft-holmer-rmcat-transport-wide-cc-extensions-01\r\na=extmap:4 urn:ietf:params:rtp-hdrext:sdes:mid\r\na=sendrecv\r\na=msid:3c28addc-03b7-4170-b5cd-535bfe767e75 38c455bc-3727-4129-b336-8cd2c6a68486\r\na=rtcp-mux\r\na=rtcp-rsize\r\na=rtpmap:111 opus/48000/2\r\na=rtcp-fb:111 transport-cc\r\na=fmtp:111 minptime=10;useinbandfec=1\r\na=rtpmap:63 red/48000/2\r\na=fmtp:63 111/111\r\na=rtpmap:9 G722/8000\r\na=rtpmap:0 PCMU/8000\r\na=rtpmap:8 PCMA/8000\r\na=rtpmap:110 telephone-event/48000\r\na=rtpmap:126 telephone-event/8000\r\na=ssrc:2430753100 cname:MPddPt/R2ioP4vCm\r\na=ssrc:2430753100 msid:3c28addc-03b7-4170-b5cd-535bfe767e75 38c455bc-3727-4129-b336-8cd2c6a68486\r\n",
     "sdp_type": "answer"
 }
}'
