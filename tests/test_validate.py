# SPDX-License-Identifier: AGPL-3.0-only
"""Exercise catalogue policy against complete package fixtures."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.validate import STEAMCMD_BOOTSTRAP, validate


class CataloguePolicyTests(unittest.TestCase):
    def check_package(self, metadata=None, service=None, slug='example'):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            app = root / 'apps' / slug
            app.mkdir(parents=True)
            (app / 'icon.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
            (app / 'nex.yaml').write_text(yaml.safe_dump({
                'x-nex': {'name': 'Example', 'summary': 'Fixture', 'category': 'tools',
                          **(metadata or {})},
                'services': {'example': {'image': 'example:latest', **(service or {})}},
            }))
            with contextlib.redirect_stdout(io.StringIO()):
                return validate(root)

    def test_upstream_nested_storage_paths(self):
        for volume in ('${DATA}:/data', '${DATA}:/var/www/html',
                       '${CONFIG}:/etc/pihole', '${MEDIA}:/srv/media:ro',
                       '${DATA}:/opt/Game Server/data',
                       '${DATA}:/var/lib/app-data_2'):
            with self.subTest(volume=volume):
                self.assertEqual(self.check_package(service={'volumes': [volume]}), 1)

    def test_storage_still_requires_operator_selected_folder_and_safe_target(self):
        for volume in ('/srv/data:/data', 'data:/data', '${DATA}:relative',
                       '${DATA}:/', '${DATA}:/var/../data', '${DATA}:/./data',
                       '${DATA}:/var//data', '${DATA}:/data:rw', '${DATA}:/data:ro:extra'):
            with self.subTest(volume=volume):
                with self.assertRaises(AssertionError):
                    self.check_package(service={'volumes': [volume]})

    def test_explicit_scalable_services(self):
        self.assertEqual(self.check_package({'scale': ['example']}), 1)
        self.assertEqual(self.check_package({'scale': ['example'], 'scalable': True}), 1)
        for metadata in ({'scalable': True}, {'scale': 'example'},
                         {'scale': ['other']}, {'scale': ['example', 'example']},
                         {'scale': ['example'], 'scalable': False}):
            with self.subTest(metadata=metadata), self.assertRaises(AssertionError):
                self.check_package(metadata)

    def test_copies_are_chosen_at_install(self):
        with self.assertRaises(AssertionError):
            self.check_package({'scale': ['example']}, {'deploy': {'replicas': 2}})

    def test_named_game_image_is_limited_to_its_catalogue_package(self):
        image = {'image': 'ghcr.io/gameservermanagers/gameserver:tf2'}
        self.assertEqual(self.check_package({'category': 'games'}, image, 'team-fortress-2'), 1)
        for category, slug in (('tools', 'team-fortress-2'), ('games', 'example')):
            with self.subTest(category=category, slug=slug), self.assertRaises(AssertionError):
                self.check_package({'category': category}, image, slug)

    def test_reviewed_release_is_limited_to_its_catalogue_package(self):
        image = {'image': 'athou/commafeed:latest-h2'}
        self.assertEqual(self.check_package(service=image, slug='commafeed'), 1)
        with self.assertRaisesRegex(AssertionError, 'reviewed package-specific tag'):
            self.check_package(service=image, slug='example')

    def test_game_ports_require_primary_app_network(self):
        metadata = {'category': 'games'}
        self.assertEqual(self.check_package(metadata, {'expose': ['7777/udp']}), 1)
        with self.assertRaisesRegex(AssertionError, 'primary app network'):
            self.check_package(metadata, {'ports': ['7777:7777/udp']})

    def test_options_use_only_keys_core_reads(self):
        service = {'environment': {'MODE': '${MODE:-fast}'}}
        option = {'label': 'Mode', 'help': 'Leave empty for fast.', 'type': 'text'}
        self.assertEqual(self.check_package({'options': {'MODE': option}}, service), 1)
        self.assertEqual(self.check_package({'options': {'MODE': 'Mode'}}, service), 1)
        for extra in ({'default': 'fast'}, {'required': False}):
            with self.subTest(extra=extra), self.assertRaisesRegex(AssertionError, 'Core ignores option keys'):
                self.check_package({'options': {'MODE': {**option, **extra}}}, service)

    def test_password_generate_formats_follow_core(self):
        service = {'environment': {'KEY': '${KEY}'}}
        def option(generate, kind='password'):
            return {'options': {'KEY': {'label': 'Key', 'type': kind, 'generate': generate}}}
        for generate in ({'format': 'hex', 'length': 64}, {'format': 'alnum', 'length': 32, 'max_length': 32},
                         {'format': 'password', 'length': 20, 'min_length': 12},
                         {'format': 'base64', 'bytes': 32, 'prefix': 'base64:'},
                         {'format': 'base64url', 'prefix': 'k4.local.'}, {'format': 'uuid'}):
            with self.subTest(generate=generate):
                self.assertEqual(self.check_package(option(generate), service), 1)
        for generate in ({'format': 'words'}, 'hex', {'format': 'hex', 'bytes': 32},
                         {'format': 'base64', 'length': 44}, {'format': 'alnum', 'length': 4},
                         {'format': 'alnum', 'length': 20, 'min_length': 30}, {'format': 'base64', 'bytes': 8},
                         {'format': 'hex', 'prefix': 'two words'}, {'format': 'uuid', 'length': 36},
                         {'format': 'alnum', 'length': 20, 'max_length': 600}):
            with self.subTest(generate=generate), self.assertRaises(AssertionError):
                self.check_package(option(generate), service)
        with self.assertRaisesRegex(AssertionError, 'type: password'):
            self.check_package(option({'format': 'hex'}, 'text'), service)
        with self.assertRaisesRegex(AssertionError, 'takes no'):
            self.check_package(option({'format': 'hex'}), {'environment': {'KEY': '${KEY:-changeme}'}})

    def test_steamcmd_bootstrap_matches_reviewed_copy(self):
        command = ['/bin/bash', '-ec', f'{STEAMCMD_BOOTSTRAP}\n\nnex_steamcmd_update 1234 linux']
        self.assertEqual(self.check_package({'category': 'games'}, {'command': command}), 1)
        command[-1] = command[-1].replace('attempt in 1 2 3', 'attempt in 1')
        with self.assertRaisesRegex(AssertionError, 'refresh the embedded SteamCMD bootstrap'):
            self.check_package({'category': 'games'}, {'command': command})


if __name__ == '__main__':
    unittest.main()
