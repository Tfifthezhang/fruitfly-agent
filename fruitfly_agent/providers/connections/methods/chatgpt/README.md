# Use a ChatGPT plan

[Up: Connections](../../README.md) · [Authentication](../../../auth/README.md)

Choose Subscription · ChatGPT → Continue with ChatGPT. Complete official consent
in the system browser. The loopback listener starts first, binds 127.0.0.1 and uses
an available port. TTY authorization returns automatically when the callback
completes; numbered fallback supports Continue and hidden manual callback input.
Cancel/timeout closes the listener. No website or intermediary login service is
hosted by FruitFlyAgent.

`auth.py` uses the official public-client dynamic registration flow, an opaque
stable host ID, fresh state/nonce/PKCE, and the issued client ID for exchange and
returning sign-in. ID tokens require a verified RS256 signature from OpenAI's
published keys, issuer, audience, expiry, subject and login nonce. Account
registrations remain separate even if email labels match. Plan consent is checked
separately from identity; missing consent cannot authorize inference. Renewal is
serialized, validates returned identity and atomically replaces rotating tokens.
Sign-out attempts official renewable-session revocation and clears tokens locally.

`catalog.py` lists the selected account's visible model slugs. Missing documented
context/output limits require explicit confirmation; limits are not guessed from
model names. `requests.py` targets public `/v1/responses`, sets `store: false`,
streams through a terminal event and groups client function tools in a namespace.
It never calls legacy ChatGPT backend endpoints. Unsupported options fail before
construction; it omits the unsupported output-limit field and reserves the model's
confirmed maximum for context admission. No hosted tools or WebSocket continuation
are added. Existing Responses codecs retain reasoning, images and tool results.

Public access applies to eligible open-source/local integrations. Paid or remotely
hosted applications have a separate application path. A successful offline test
is not evidence of eligibility, quota or remote compatibility.

References: [integration scope](https://developers.openai.com/siwc/token-sharing-open-source),
[sign-in and validation](https://developers.openai.com/siwc/token-sharing-open-source/sign-in),
[accounts and renewal](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions),
[request limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations).

Checks: `tests.providers.test_auth`, `tests.providers.test_subscription_requests`.
Real authorization and inference are explicit user operations; inference consumes
shared plan allowance. No account credentials are imported from other clients.

For an SSH session without a browser, select **Authorize in another browser…**
and open the displayed link on your computer. After consent, paste the complete
callback URL into the hidden prompt, even if the browser cannot reach the
loopback page. Keep this URL out of chat and logs. The server validates the
callback against the active attempt and stores the resulting authorization on
the server. This flow requires no public callback listener.
