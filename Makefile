.PHONY: seed fetch build all serve serve-static pulse ticker symbolmap clean check test-stream qa vapt verify dist deploy
#
# SITE_URL is REQUIRED for any target that publishes (build/all/pulse): it is
# baked into sitemap.xml, robots.txt and feed.xml, and the build refuses a
# placeholder rather than shipping unresolvable URLs.
#
#   SITE_URL=https://brokerlens.in make all
#

seed:        ; python3 -m pipeline.run seed
fetch:       ; python3 -m pipeline.run fetch
build:       ; python3 -m pipeline.run build
all:         ; python3 -m pipeline.run all
pulse:       ; python3 -m pipeline.run pulse
ticker:      ; python3 -m pipeline.run ticker
symbolmap:   ; python3 -m pipeline.symbolmap

# Static site + live SSE stream (needs an always-on process).
serve:       ; python3 server/devserver.py --port $(or $(PORT),8000)
# Static only; the front end falls back to polling ticker.json.
serve-static: ; python3 server/devserver.py --port $(or $(PORT),8000) --no-stream

# Compile-check every module and confirm the published payloads parse.
check:
	@python3 -m compileall -q pipeline server && echo "python ok"
	@python3 -c "import json,glob; [json.load(open(f)) for f in glob.glob('site/data/**/*.json',recursive=True)]; print('json ok')"

# Exercise the delta detection and SSE fan-out without needing a live market.
test-stream:
	@cd server && python3 -c "\
from quotes import Hub;\
h=Hub(); h.seed_from_disk(); sub,snap=h.subscribe();\
base=snap['feeds']['NSE']['instruments'][:2];\
assert h.apply('NSE', instruments=[dict(q) for q in base])==0, 'unchanged must not push';\
moved=[dict(base[0], last=base[0]['last']+1)]+[dict(q) for q in base[1:]];\
assert h.apply('NSE', instruments=moved)==1, 'moved price must push';\
ev,p=sub.get(timeout=2); assert ev=='quotes' and len(p['instruments'])==1;\
print('stream ok: delta detection + fan-out')"

clean:       ; rm -rf data/cache data/_ingest.json

# A deployable copy of site/, with junk that must never reach a public host
# stripped. .DS_Store is a binary directory index that leaks every filename,
# and static hosts serve it before applying SPA rewrites.
# .vercel/ holds the project link; preserving it keeps repeat deploys pointed at
# the same project instead of creating a new one named after the folder.
dist: check
	@mkdir -p dist && find dist -mindepth 1 -maxdepth 1 ! -name '.vercel' ! -name '.env.local' -exec rm -rf {} +
	@cd site && tar --exclude='.DS_Store' --exclude='._*' --exclude='.git*' -cf - . | (cd ../dist && tar -xf -)
	@find dist -name '.DS_Store' -delete
	@echo "dist/ ready to upload ($$(find dist -type f | wc -l | tr -d ' ') files)"

# Functional QA. Pass URL=... to include the live server + SSE checks.
qa:
	@python3 tests/qa_e2e.py $(if $(URL),--url $(URL),--url http://127.0.0.1:8000)

# Security assessment of our own stack. SKIP_DOS=1 to omit the flood probes.
vapt:
	@python3 tests/vapt.py $(if $(URL),--url $(URL),--url http://127.0.0.1:8000) $(if $(SKIP_DOS),--skip-dos,)

# Everything a deploy should have to pass.
verify: check qa vapt
	@echo "verification complete"

# One command to publish. Refreshes data from the primary sources, drops
# anything still flagged sample, rebuilds the deployable copy, and pushes it.
# Requires a logged-in Vercel CLI (`vercel login`) and a linked dist/.
deploy:
	@SITE_URL=$(or $(SITE_URL),https://brokerlens.in) PUBLISH_MODE=production python3 -m pipeline.run all
	@$(MAKE) dist
	@cp site/vercel.json dist/vercel.json
	@cd dist && vercel deploy --prod --yes
	@echo "deployed. verify: curl -sI https://brokerlens.in | head -1"
