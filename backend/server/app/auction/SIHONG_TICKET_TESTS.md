# Sihong Ticket API Test Guide

Base URL:

```text
http://127.0.0.1:8000
```

Assume:

- `ADMIN_TOKEN` is a valid admin bearer token.
- `REP_TOKEN` is a valid rep bearer token.
- `AUCTION_ID=current`.

## 1) ST-142 Invite participants + ST-138 Join window

Add invites:

```bash
curl -X POST "http://127.0.0.1:8000/auctions/current/invites" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"userIds":["<rep_user_id_1>","<rep_user_id_2>"]}'
```

Get invites:

```bash
curl "http://127.0.0.1:8000/auctions/current/invites" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Rep joins auction:

```bash
curl -X POST "http://127.0.0.1:8000/auctions/current/join" \
  -H "Authorization: Bearer $REP_TOKEN"
```

Expected:

- Joined once within first 30 minutes: success.
- Reconnect after 30 minutes if already joined: success (`reconnected=true`).
- First-time join after 30 minutes: 403.
- Not invited rep: 403.

## 2) ST-146 Auto timer extension on late bids

Place bid (when <=10 min left):

```bash
curl -X POST "http://127.0.0.1:8000/bids/place" \
  -H "Authorization: Bearer $REP_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"item_id":"<item_object_id>"}'
```

Check auction state extensions:

```bash
curl "http://127.0.0.1:8000/auctions/current/state" \
  -H "Authorization: Bearer $REP_TOKEN"
```

Expected:

- `endsAt` increased by up to 180 seconds.
- total auto-extension is capped at `scheduledEndsAt + 900s` (15 minutes).
- new extensions entry with:
  - `reason=late_bid`
  - `deltaSeconds` can be `<180` when hitting cap
  - `bidId` present.

## 3) ST-140 Manual admin timer extension

```bash
curl -X POST "http://127.0.0.1:8000/auctions/current/extend" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"deltaSeconds":120,"reason":"admin"}'
```

Expected:

- `endsAt` moved forward by 120 seconds.
- extension history appended.

## 4) ST-143 Sort participants by bidding power

```bash
curl "http://127.0.0.1:8000/auctions/current/participants?sort=biddingPower&order=desc" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Expected each row:

- `userId`
- `name`
- `kogbucksTotal`
- `kogbucksHeld`
- `biddingPower`

Ordered descending by `biddingPower`.

## 5) ST-135 Admin KBs dashboard view

```bash
curl "http://127.0.0.1:8000/auctions/current/dashboard/kbs" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Expected fields:

- `invitedCount`
- `joinedCount`
- `notBidYetCount`
- `topByBiddingPower`

## 6) ST-141 Bid-time messages + final results

Rep messages during bidding:

```bash
curl "http://127.0.0.1:8000/auctions/current/messages/my" \
  -H "Authorization: Bearer $REP_TOKEN"
```

Expected message types:

- `LEADING` (you are leading)
- `OUTBID` (you were outbid)

Rep final results:

```bash
curl "http://127.0.0.1:8000/auctions/current/my-results" \
  -H "Authorization: Bearer $REP_TOKEN"
```

Expected:

- `won`: items won by the rep
- `lost`: items where rep bid but did not win

## Optional auction lifecycle checks

Start:

```bash
curl -X POST "http://127.0.0.1:8000/auctions/start" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

End:

```bash
curl -X POST "http://127.0.0.1:8000/auctions/current/end" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

## 7) Phase 2 WebSocket smoke test (snapshot + live events)

Install `wscat` (one-time):

```bash
npm i -g wscat
```

Open rep socket:

```bash
wscat -c "ws://127.0.0.1:8000/ws/auctions/current?token=$REP_TOKEN"
```

Expected first server events:

- `auction.connected`
- `auction.snapshot` (includes `state` + `my_messages`)

Send ping:

```json
{"type":"ping"}
```

Expected:

- `pong`

Request re-sync snapshot manually:

```json
{"type":"sync.request"}
```

Expected:

- new `auction.snapshot` payload

Trigger state-changing actions from HTTP in another terminal:

- `POST /auctions/current/extend` -> expect `auction.timer_extended` + `auction.state_updated`
- `POST /bids/place` -> expect `bid.placed` + `auction.state_updated`
- `POST /auctions/current/end` -> expect `auction.ended` + `auction.state_updated`

## 8) Frontend reconnect guideline (Phase 2)

Recommended client behavior:

- use exponential backoff reconnect (1s, 2s, 4s, max 10s)
- on reconnect, call `GET /auctions/{auction_id}/state` once to hard-resync
- after WS opens, also send `{"type":"sync.request"}` to get `auction.snapshot`

Minimal JS sketch:

```javascript
function connectAuctionWs({ auctionId, token, onEvent }) {
  let tries = 0;
  let ws;

  const open = () => {
    ws = new WebSocket(`ws://127.0.0.1:8000/ws/auctions/${auctionId}?token=${token}`);
    ws.onopen = async () => {
      tries = 0;
      await fetch(`http://127.0.0.1:8000/auctions/${auctionId}/state`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      ws.send(JSON.stringify({ type: "sync.request" }));
    };
    ws.onmessage = (evt) => onEvent(JSON.parse(evt.data));
    ws.onclose = () => {
      const delay = Math.min(10000, 1000 * (2 ** tries++));
      setTimeout(open, delay);
    };
  };

  open();
  return () => ws && ws.close();
}
```

## 9) Phase 3 WS outbox checks (crash-safe delivery)

Outbox collection defaults to `ws_outbox` (env: `WS_OUTBOX_COLLECTION_NAME`).

Check pending/sent events in Mongo (mongosh):

```javascript
db.ws_outbox.find({}, { auction_id: 1, status: 1, payload: 1, created_at: 1, sent_at: 1 }).sort({ created_at: -1 }).limit(20)
```

Expected:

- New events are inserted as `PENDING`.
- Dispatcher moves them to `SENT`.
- On temporary failure, document returns to `PENDING` with increased `attempt_count`.

Optional env tuning:

- `WS_OUTBOX_POLL_SECONDS` (default `0.25`)
- `WS_OUTBOX_BATCH_SIZE` (default `100`)
