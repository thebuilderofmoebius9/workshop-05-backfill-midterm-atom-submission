.PHONY: backfill test screenshot clean

backfill:
	python3 -m discord_backfill.cli backfill \
		--input samples/discord-export.json \
		--mirror out/mirror \
		--db out/atom-backfill.sqlite \
		--dashboard out/dashboard.html

test:
	python3 -m unittest discover -s tests -v

screenshot: backfill
	mkdir -p artifacts
	google-chrome --headless --disable-gpu --no-sandbox --window-size=1440,1000 \
		--screenshot=artifacts/dashboard.png \
		file://$(PWD)/out/dashboard.html

clean:
	rm -rf out artifacts
