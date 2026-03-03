.PHONY: all install

all:

install:
	install -m644 ./sync.py /opt/pve-traefik-sync/sync.py
	install -m644 ./pve-traefik-sync.service /etc/systemd/system/pve-traefik-sync.service
	install -m644 ./pve-traefik-sync.timer /etc/systemd/system/pve-traefik-sync.timer

daemon-reload:
	sudo systemctl daemon-reload
	sudo systemctl enable --now pve-traefik-sync.timer