#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Validate catalogue policy; optionally exercise the actual Nex Core parser/renderer."""
import argparse
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LATEST_IMAGE = re.compile(r"^[a-z0-9./_-]+:latest$")
STEAMCMD_BOOTSTRAP = (ROOT / 'scripts' / 'steamcmd-bootstrap.sh').read_text().strip().replace('$', '$$')
# Reviewed exceptions for upstream game and release tags.
GAME_IMAGES = {
    'ark-survival-ascended': 'ghcr.io/gregoirechauvet/ark-server:proton-10',
    'assaultcube': 'ghcr.io/ptero-eggs/yolks:debian',
    'astro-colony': 'ghcr.io/ptero-eggs/steamcmd:debian',
    'avorion': 'ghcr.io/gameservermanagers/gameserver:av',
    'battalion-legacy': 'ghcr.io/ptero-eggs/steamcmd:debian',
    'black-mesa': 'ghcr.io/gameservermanagers/gameserver:bmdm',
    'brickadia': 'ghcr.io/ptero-eggs/steamcmd:debian',
    'citadel-forged-with-fire': 'ghcr.io/ich777/steamcmd:citadelfwf',
    'classicube-mcgalaxy': 'ghcr.io/ptero-eggs/yolks:mono_latest',
    'clone-hero': 'ghcr.io/ptero-eggs/yolks:debian',
    'colony-survival': 'ghcr.io/gameservermanagers/gameserver:col',
    'counter-strike-1-6': 'ghcr.io/gameservermanagers/gameserver:cs',
    'counter-strike-source': 'ghcr.io/gameservermanagers/gameserver:css',
    'craftopia': 'ghcr.io/gameservermanagers/gameserver:ct',
    'cryofall': 'docker.io/atomictorch/cryofall-server:1.33',
    'cs2d': 'ghcr.io/ptero-eggs/yolks:debian',
    'et-legacy': 'ghcr.io/gameservermanagers/gameserver:etl',
    'factorio': 'docker.io/factoriotools/factorio:stable',
    'fistful-of-frags': 'ghcr.io/gameservermanagers/gameserver:fof',
    'foundry-vtt': 'ghcr.io/felddy/foundryvtt:release',
    'half-life-2-deathmatch': 'ghcr.io/gameservermanagers/gameserver:hl2dm',
    'half-life-deathmatch': 'ghcr.io/gameservermanagers/gameserver:hldm',
    'holdfast': 'ghcr.io/ptero-eggs/steamcmd:debian',
    'hurtworld': 'ghcr.io/gameservermanagers/gameserver:hw',
    'insurgency-sandstorm': 'ghcr.io/gameservermanagers/gameserver:inss',
    'iosoccer': 'ghcr.io/gameservermanagers/gameserver:ios',
    'just-cause-3-multiplayer': 'ghcr.io/gameservermanagers/gameserver:jc3',
    'kerbal-space-program-dmp': 'ghcr.io/ptero-eggs/yolks:mono_latest',
    'killing-floor-2': 'ghcr.io/gameservermanagers/gameserver:kf2',
    'kissmp': 'ghcr.io/ptero-eggs/yolks:debian',
    'left-4-dead': 'ghcr.io/gameservermanagers/gameserver:l4d',
    'left-4-dead-2': 'ghcr.io/gameservermanagers/gameserver:l4d2',
    'midnight-ghost-hunt': 'ghcr.io/ptero-eggs/steamcmd:proton',
    'mindustry': 'ghcr.io/ptero-eggs/yolks:java_21',
    'minecraft-arclight': 'ghcr.io/itzg/minecraft-server:java21',
    'minecraft-attack-of-the-b-team': 'ghcr.io/itzg/minecraft-server:java8',
    'minecraft-blightfall': 'ghcr.io/itzg/minecraft-server:java8',
    'minecraft-curseforge': 'ghcr.io/itzg/minecraft-server:java21',
    'minecraft-forge': 'ghcr.io/itzg/minecraft-server:java21',
    'minecraft-ftb': 'ghcr.io/itzg/minecraft-server:java21',
    'minecraft-glowstone': 'ghcr.io/itzg/minecraft-server:java8',
    'minecraft-hexxit': 'ghcr.io/itzg/minecraft-server:java8',
    'minecraft-levilamina': 'ghcr.io/liteldev/levilamina-server:latest-wine',
    'minecraft-magma': 'ghcr.io/itzg/minecraft-server:java17',
    'minecraft-modrinth': 'ghcr.io/itzg/minecraft-server:java21',
    'minecraft-mohist': 'ghcr.io/itzg/minecraft-server:java17',
    'minecraft-nanolimbo': 'ghcr.io/itzg/minecraft-server:java21',
    'minecraft-neoforge': 'ghcr.io/itzg/minecraft-server:java21',
    'minecraft-nukkit': 'ghcr.io/itzg/minecraft-server:java17',
    'minecraft-quilt': 'ghcr.io/itzg/minecraft-server:java21',
    'minecraft-spigot': 'ghcr.io/itzg/minecraft-server:java25-jdk',
    'minecraft-spongeforge': 'ghcr.io/itzg/minecraft-server:java21',
    'minecraft-tekkit': 'ghcr.io/itzg/minecraft-server:java8',
    'minecraft-tekkit-2': 'ghcr.io/itzg/minecraft-server:java8',
    'minecraft-tekkit-classic': 'ghcr.io/itzg/minecraft-server:java8',
    'minecraft-tekkit-legends': 'ghcr.io/itzg/minecraft-server:java8',
    'minecraft-tekkit-smp': 'ghcr.io/itzg/minecraft-server:java8',
    'minecraft-the-1-12-2-pack': 'ghcr.io/itzg/minecraft-server:java8',
    'minecraft-the-1-7-10-pack': 'ghcr.io/itzg/minecraft-server:java8',
    'minecraft-viaaas': 'ghcr.io/itzg/minecraft-server:java21',
    'mordhau': 'ghcr.io/gameservermanagers/gameserver:mh',
    'necesse': 'ghcr.io/gameservermanagers/gameserver:nec',
    'night-of-the-dead': 'ghcr.io/ptero-eggs/steamcmd:proton',
    'nightingale': 'ghcr.io/ekman/nightingale:1',
    'no-love-lost': 'ghcr.io/ptero-eggs/steamcmd:proton',
    'no-more-room-in-hell': 'ghcr.io/gameservermanagers/gameserver:nmrih',
    'no-one-survived': 'ghcr.io/ptero-eggs/steamcmd:proton',
    'nuclear-option': 'ghcr.io/ptero-eggs/steamcmd:debian',
    'onset': 'ghcr.io/ptero-eggs/steamcmd:debian',
    'openmp': 'ghcr.io/ptero-eggs/games:samp',
    'openra-dune-2000': 'ghcr.io/ptero-eggs/steamcmd:debian',
    'openra-red-alert': 'ghcr.io/ptero-eggs/steamcmd:debian',
    'openra-tiberian-dawn': 'ghcr.io/ptero-eggs/steamcmd:debian',
    'openttd': 'docker.io/bateau/openttd:15.3',
    'operation-harsh-doorstop': 'ghcr.io/gameservermanagers/gameserver:ohd',
    'path-of-titans': 'ghcr.io/ptero-eggs/steamcmd:debian',
    'pavlov-vr': 'ghcr.io/gameservermanagers/gameserver:pvr',
    'pixark': 'ghcr.io/ptero-eggs/steamcmd:proton',
    'plains-of-pain': 'ghcr.io/ptero-eggs/steamcmd:debian',
    'puck': 'ghcr.io/ptero-eggs/steamcmd:debian',
    'quake-live': 'ghcr.io/gameservermanagers/gameserver:ql',
    'rimworld-open-world': 'ghcr.io/ptero-eggs/yolks:dotnet_10',
    'rising-world': 'ghcr.io/gameservermanagers/gameserver:rw',
    'scp-secret-laboratory': 'ghcr.io/gameservermanagers/gameserver:scpsl',
    'solace-crafting': 'ghcr.io/ptero-eggs/steamcmd:debian',
    'soldat': 'ghcr.io/ptero-eggs/steamcmd:debian',
    'soldat-2': 'ghcr.io/ptero-eggs/steamcmd:debian',
    'sons-of-the-forest': 'ghcr.io/ich777/steamcmd:sonsoftheforest',
    'squad': 'ghcr.io/gameservermanagers/gameserver:squad',
    'squad-44': 'ghcr.io/gameservermanagers/gameserver:squad44',
    'starbound': 'ghcr.io/ich777/steamcmd:starbound',
    'sven-coop': 'ghcr.io/gameservermanagers/gameserver:sven',
    'team-fortress-2': 'ghcr.io/gameservermanagers/gameserver:tf2',
    'team-fortress-2-classic': 'ghcr.io/gameservermanagers/gameserver:tf2c',
    'terraria-tmodloader': 'docker.io/passivelemon/terraria-docker:tmodloader-latest',
    'terraria-tshock': 'ghcr.io/pryaxis/tshock:stable',
    'terratech-worlds': 'ghcr.io/ich777/steamcmd:terratechworlds',
    'the-forest': 'ghcr.io/ich777/steamcmd:theforest',
    'unturned': 'ghcr.io/gameservermanagers/gameserver:unt',
    'vein': 'ghcr.io/ich777/steamcmd:vein',
    'veloren': 'registry.gitlab.com/veloren/veloren/server-cli:weekly',
    'wurm-unlimited': 'ghcr.io/ich777/steamcmd:wurmunlimited',
}
# Reviewed upstream releases and image variants for other catalogue packages.
RELEASE_IMAGES = {
    'affine': ('ghcr.io/toeverything/affine:stable',),
    'aptabase': ('ghcr.io/aptabase/aptabase:main',),
    'authentik': ('ghcr.io/goauthentik/server:2026.8.5',),
    'automad': ('docker.io/automad/automad:v2',),
    'azimutt': ('ghcr.io/azimuttapp/azimutt:main',),
    'baikal': ('ghcr.io/aalmenar/baikal:0.13.0-nginx',),
    'bewcloud': ('ghcr.io/bewcloud/bewcloud:v4.23.1',),
    'bitcoin-core': ('docker.io/lncm/bitcoind:v28.0',),
    'bitmagnet': ('ghcr.io/bitmagnet-io/bitmagnet:v0.10.1',),
    'bluesky-pds': ('ghcr.io/bluesky-social/pds:0.4.5051',),
    'booklogr': ('docker.io/mozzo/booklogr-web:v1.12.0', 'docker.io/mozzo/booklogr:v1.12.0'),
    'btcpay-server': ('docker.io/btcpayserver/btcpayserver:2.4.6',),
    'budget-board': ('ghcr.io/teelur/budget-board/client:v3', 'ghcr.io/teelur/budget-board/server:v3'),
    'chevereto': ('docker.io/chevereto/chevereto:4',),
    'cockpit-cms': ('docker.io/cockpithq/cockpit:core-latest',),
    'comfyui': ('ghcr.io/romkey/comfyui-docker:0.38.0-cpu',),
    'commafeed': ('athou/commafeed:latest-h2',),
    'coral': ('docker.io/coralproject/talk:9.7.0',),
    'cronicle': ('docker.io/soulteary/cronicle:0.9.80',),
    'ebook2audiobook': ('docker.io/athomasson2/ebook2audiobook:cpu',),
    'elabftw': ('docker.io/elabftw/elabimg:stable',),
    'elasticsearch': ('docker.elastic.co/elasticsearch/elasticsearch:9.5.3',),
    'ersatztv-legacy': ('ghcr.io/ersatztv/legacy:v26.12.0',),
    'featbit': ('docker.io/featbit/featbit-api-server:6.1.2', 'docker.io/featbit/featbit-evaluation-server:6.1.2', 'docker.io/featbit/featbit-ui:6.1.2'),
    'fider': ('docker.io/getfider/fider:stable',),
    'filebrowser-quantum': ('ghcr.io/gtsteffaniak/filebrowser:stable',),
    'fittrackee': ('fittrackee/fittrackee:v1.3.7',),
    'flipt': ('ghcr.io/flipt-io/flipt:v2',),
    'freescout': ('docker.io/nfrastack/freescout:2.2.25',),
    'frigate': ('ghcr.io/blakeblackshear/frigate:stable',),
    'frp': ('ghcr.io/fatedier/frps:v0.71.0',),
    'garage': ('dxflrs/garage:v2.0.0',),
    'gatus': ('ghcr.io/twin/gatus:stable',),
    'gitingest': ('ghcr.io/coderamp-labs/gitingest:v0.3.1',),
    'glitchsoc': ('ghcr.io/glitch-soc/mastodon-streaming:v4.7.5', 'ghcr.io/glitch-soc/mastodon:v4.7.5'),
    'graylog': ('docker.io/graylog/graylog:7.2',),
    'hasura': ('docker.io/hasura/graphql-engine:v2.48.4',),
    'headscale': ('docker.io/headscale/headscale:0.29.5',),
    'hedgedoc': ('quay.io/hedgedoc/hedgedoc:1.12.0',),
    'heyform': ('docker.io/heyform/community-edition:v3.0.6',),
    'hi-events': ('docker.io/daveearley/hi.events-all-in-one:v2.2.0',),
    'homelable': ('ghcr.io/pouzor/homelable-backend:3.6.0', 'ghcr.io/pouzor/homelable-frontend:3.6.0'),
    'humhub': ('docker.io/humhub/humhub:stable',),
    'immich': ('docker.io/valkey/valkey:9', 'ghcr.io/immich-app/immich-machine-learning:release', 'ghcr.io/immich-app/immich-server:release', 'ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0'),
    'influxdb': ('docker.io/library/influxdb:3.12.2-core',),
    'ironcalc': ('ghcr.io/ironcalc/ironcalc-caddy:0.9.1', 'ghcr.io/ironcalc/ironcalc-server:0.9.1'),
    'jenkins': ('docker.io/jenkins/jenkins:lts-jdk21',),
    'kan': ('ghcr.io/kanbn/kan:0.7.0',),
    'keeper-sh': ('ghcr.io/ridafkih/keeper-standalone:2',),
    'kimai': ('docker.io/kimai/kimai2:2.72.0',),
    'limesurvey': ('docker.io/adamzammit/limesurvey:7.10.0',),
    'litellm': ('ghcr.io/berriai/litellm:main-stable',),
    'llama-cpp': ('ghcr.io/ggml-org/llama.cpp:server',),
    'mautic': ('docker.io/mautic/mautic:7-apache',),
    'memos': ('docker.io/neosmemo/memos:stable',),
    'mixpost': ('docker.io/inovector/mixpost:v2.6.0',),
    'monetr': ('ghcr.io/monetr/monetr:1.22.2',),
    'music-assistant': ('ghcr.io/music-assistant/server:2.10.12',),
    'octobot': ('drakkarsoftware/octobot:stable',),
    'open-notebook': ('lfnovo/open_notebook:v1-latest',),
    'open-webui': ('ghcr.io/open-webui/open-webui:v0.13.4',),
    'openpanel': ('docker.io/lindesvard/openpanel-api:2', 'docker.io/lindesvard/openpanel-dashboard:2', 'docker.io/lindesvard/openpanel-worker:2'),
    'openproject': ('docker.io/openproject/openproject:17',),
    'openremote': ('docker.io/openremote/postgresql:latest-slim',),
    'opensign': ('docker.io/opensign/opensign:main', 'docker.io/opensign/opensignserver:main'),
    'outline-server': ('quay.io/outline/shadowbox:stable',),
    'owncloud': ('docker.io/owncloud/server:11.1.0',),
    'passbolt': ('passbolt/passbolt:latest-ce',),
    'peergos': ('ghcr.io/peergos/web-ui:master',),
    'peertube': ('docker.io/chocobozzz/peertube:v8.3.2',),
    'pgdog': ('ghcr.io/pgdogdev/pgdog:v0.1.65',),
    'plausible-analytics': ('ghcr.io/plausible/community-edition:v3.2.1',),
    'portabase': ('docker.io/portabase/portabase:1.36.2',),
    'portainer': ('portainer/portainer-ce:lts',),
    'postal': ('ghcr.io/postalserver/postal:3.4.0',),
    'prefect': ('docker.io/prefecthq/prefect:3-latest',),
    'pretix': ('docker.io/pretix/standalone:stable',),
    'prisme-analytics': ('docker.io/prismelabs/analytics:v0.20.0',),
    'pulse': ('rcourtman/pulse:v6.8.0',),
    'radicale': ('ghcr.io/kozea/radicale:stable',),
    'recyclarr': ('ghcr.io/recyclarr/recyclarr:8.8.1',),
    'redaxo': ('docker.io/friendsofredaxo/redaxo:5',),
    'reitti': ('docker.io/dedicatedcode/reitti-tile-cache:5', 'docker.io/dedicatedcode/reitti:5'),
    'ryot': ('ignisda/ryot:v10',),
    'screego': ('docker.io/screego/server:1.12.6',),
    'scrutiny': ('ghcr.io/analogj/scrutiny:latest-web',),
    'seafile': ('docker.io/seafileltd/seafile-mc:14.0.9',),
    'shellhub': ('docker.io/shellhubio/server:v0.30.1', 'docker.io/shellhubio/ui:v0.30.1', 'docker.io/valkey/valkey:9.1-alpine'),
    'silverbullet': ('ghcr.io/silverbulletmd/silverbullet:v2',),
    'srs': ('docker.io/ossrs/srs:6',),
    'stalwart': ('docker.io/stalwartlabs/stalwart:v1',),
    'strapi': ('docker.io/elestio/strapi-production:v5.33.0',),
    'tandoor': ('ghcr.io/tandoorrecipes/recipes:2.7.3',),
    'teable': ('ghcr.io/teableio/teable:release.2026-11-13T02-21-01Z.3890',),
    'temporal': ('docker.io/temporalio/server:1.32.2',),
    'tooljet': ('docker.io/tooljet/tooljet-ce:ce-lts-latest',),
    'typesense': ('docker.io/typesense/typesense:30.2',),
    'usesend': ('docker.io/usesend/usesend:v1.10.3',),
    'vector': ('docker.io/timberio/vector:latest-debian',),
    'vllm': ('vllm/vllm-openai-cpu:latest-x86_64',),
    'wiki-js': ('ghcr.io/requarks/wiki:2',),
    'writefreely': ('ghcr.io/writefreely/writefreely:v0.17.1',),
    'xwiki': ('docker.io/library/xwiki:stable-postgres-tomcat',),
    'yuvomi': ('ghcr.io/ulsklyc/yuvomi:2.80.0',),
    'zabbix': ('docker.io/zabbix/zabbix-server-pgsql:alpine-7.4-latest', 'docker.io/zabbix/zabbix-web-nginx-pgsql:alpine-7.4-latest'),
    'zen-notes': ('ghcr.io/sheshbabu/zen/zen:2.0.0',),
    'zitadel': ('ghcr.io/zitadel/zitadel:v4.16.0',),
}
REF = re.compile(r"\$\{([A-Z][A-Z0-9_]*)(?::-([^}]*))?\}")
PATH_SEGMENT = r'[A-Za-z0-9_.-]+(?: [A-Za-z0-9_.-]+)*'
VOLUME = re.compile(rf'\$\{{[A-Z][A-Z0-9_]*\}}:/{PATH_SEGMENT}(?:/{PATH_SEGMENT})*(?::ro)?')


def validate(root=ROOT):
    manifests = sorted(root.glob('apps/*/nex.yaml'))
    assert manifests, 'No packages found'
    for path in manifests:
        text = path.read_text()
        app = yaml.safe_load(text)
        meta = app['x-nex']
        assert all(meta.get(k) for k in ('name', 'summary', 'category')), path
        scaled = meta.get('scale', [])
        assert isinstance(scaled, list) and all(
            isinstance(name, str) and name in app['services'] for name in scaled
        ), (path, 'scale must list service names')
        assert len(set(scaled)) == len(scaled), (path, 'scale lists duplicate services')
        assert meta.get('scalable', bool(scaled)) is bool(scaled), (
            path, 'scalable packages must explicitly list scalable services'
        )
        icons = [p for p in (path.parent/'icon.svg', path.parent/'icon.png') if p.is_file()]
        assert len(icons) == 1, (path, 'needs exactly one of icon.svg or icon.png')
        icon = icons[0]
        assert 0 < icon.stat().st_size <= 32768, icon
        if icon.suffix == '.png':
            assert icon.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'), icon
        else:
            svg = ET.parse(icon).getroot()
            assert svg.tag == '{http://www.w3.org/2000/svg}svg', icon
            assert not any(e.tag.endswith(('script', 'foreignObject', 'image')) for e in svg.iter()), icon
        defaults = {}
        for var, default in REF.findall(text):
            if default:
                assert var not in defaults or defaults[var] == default, (path, var)
                defaults[var] = default
        ports = []
        for name, svc in app['services'].items():
            game_image = GAME_IMAGES.get(path.parent.name) if meta['category'] == 'games' else None
            assert (
                LATEST_IMAGE.fullmatch(svc['image'])
                or svc['image'] == game_image
                or svc['image'] in RELEASE_IMAGES.get(path.parent.name, ())
            ), (
                path, name, 'image must use latest or a reviewed package-specific tag'
            )
            if meta['category'] == 'games':
                assert not svc.get('ports'), (path, name, 'game ports use the primary app network')
            for field in ('command', 'entrypoint'):
                launch = svc.get(field, '')
                launch = '\n'.join(launch) if isinstance(launch, list) else launch
                if isinstance(launch, str) and 'nex_steamcmd_update' in launch:
                    assert STEAMCMD_BOOTSTRAP in launch, (path, name, 'refresh the embedded SteamCMD bootstrap')
            assert not any(k in svc for k in ('build','privileged','devices','network_mode','env_file','extends','container_name','depends_on')), (path,name)
            assert svc.get('deploy', {}).get('replicas', 1) == 1, (path,name)
            for volume in svc.get('volumes', []):
                assert VOLUME.fullmatch(volume), (path,volume)
                target = volume.split(':')[1]
                assert not any(part in ('.', '..') for part in target.split('/')), (path,volume)
            for port in svc.get('ports', []):
                expanded = REF.sub(lambda m: defaults[m[1]], port)
                published = int(expanded.split(':')[0])
                assert 1 <= published <= 65535 and published not in ports, (path,port)
                ports.append(published)
        print(f'{path.parent.name}: package policy passed')
    return len(manifests)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core', type=Path, help='Nex source checkout with internal/apps')
    args = parser.parse_args()
    count = validate()
    if args.core:
        core = args.core.resolve()
        with tempfile.TemporaryDirectory(prefix='catalogue-check-', dir=core) as folder:
            shutil.copyfile(ROOT/'scripts/check-core.go', Path(folder)/'main.go')
            subprocess.run(['go','run','.',str(ROOT)], cwd=folder, check=True)
    print(f'{count} packages validated; native runtime acceptance is separate')


if __name__ == '__main__':
    main()
