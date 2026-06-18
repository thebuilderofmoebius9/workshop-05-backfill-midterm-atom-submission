.PHONY: backfill fetch-real backfill-real test screenshot screenshot-real clean

backfill:
	python3 -m discord_backfill.cli backfill \
		--input samples/discord-export.json \
		--mirror out/mirror \
		--db out/atom-backfill.sqlite \
		--dashboard out/dashboard.html

fetch-real:
	python3 -m discord_backfill.cli fetch-discord \
		--guild-id 1512058941536735383 \
		--guild-name "Oracle School" \
		--channel-id 1512079809021214730 \
		--channel-name "free-for-all" \
		--limit 100 \
		--redact \
		--output samples/oracle-school-free-for-all-real.json

backfill-real:
	python3 -m discord_backfill.cli backfill \
		--input samples/oracle-school-free-for-all-real.json \
		--mirror out/real-mirror \
		--db out/atom-real-backfill.sqlite \
		--dashboard out/real-dashboard.html

test:
	python3 -m unittest discover -s tests -v

screenshot: backfill
	mkdir -p artifacts
	google-chrome --headless --disable-gpu --no-sandbox --window-size=1440,1000 \
		--screenshot=artifacts/dashboard.png \
		file://$(PWD)/out/dashboard.html

screenshot-real: backfill-real
	mkdir -p artifacts
	google-chrome --headless --disable-gpu --no-sandbox --window-size=1440,1000 \
		--screenshot=artifacts/real-dashboard.png \
		file://$(PWD)/out/real-dashboard.html

clean:
	rm -rf out artifacts
