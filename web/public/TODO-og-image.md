# TODO: real Open Graph banner

The layout metadata currently uses `/icon-512.png` (square) as the OG/Twitter share image — it renders
on every platform but is not the 1200x630 wide format social cards prefer.

1. Generate a 1200x630 banner: CloutHook wordmark + tagline "Hook first · Clout follows" on the
   blue/purple brand gradient (the in-house image gen can produce this).
2. Save as `web/public/og.png`.
3. In `web/src/app/layout.tsx`, replace `/icon-512.png` with `/og.png` in BOTH the `openGraph.images`
   and `twitter.images` entries (and set width 1200 / height 630).
4. Verify with https://cards-dev.twitter.com/validator and https://developers.facebook.com/tools/debug/.
