"""Resolve runner inputs into local files with auditable, credential-free provenance."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from fnmatch import fnmatchcase
from glob import glob
import hashlib
import html
import json
from pathlib import Path, PurePosixPath
import re
import shutil
from urllib.parse import parse_qs, unquote, urlsplit

SUPPORTED = {'.json', '.parquet'}
PLACEHOLDERS = {'YOUR_AWS_ACCESS_KEY_ID', 'YOUR_AWS_SECRET_ACCESS_KEY', 'YOUR_AWS_SESSION_TOKEN', 'YOUR_AWS_PROFILE'}


class InputSourceError(ValueError):
    """An input could not be resolved; do not validate a partial folder silently."""


def s3_location(value: str) -> tuple[str, str] | None:
    """Accept S3 URIs, AWS HTTPS object links and console bucket/prefix links."""
    parsed = urlsplit(value)
    if parsed.scheme == 's3':
        if parsed.query: raise InputSourceError('S3 URIs must not contain query credentials or version parameters')
        bucket, key = parsed.netloc, parsed.path.lstrip('/')
    elif parsed.scheme == 'https':
        host = parsed.hostname or ''
        if re.fullmatch(r'[a-z0-9-]+\.console\.aws\.amazon\.com', host):
            parts = parsed.path.strip('/').split('/')
            if len(parts) != 3 or parts[0] != 's3' or parts[1] not in ('buckets', 'object'):
                raise InputSourceError('Use an S3 bucket/prefix console link or s3://bucket/key')
            bucket = parts[2]
            key = parse_qs(parsed.query).get('prefix', [''])[0]
            if parts[1] == 'buckets' and key and not key.endswith('/'): key += '/'
        else:
            virtual = re.fullmatch(r'(.+)\.s3(?:[.-][a-z0-9-]+)?\.amazonaws\.com(?:\.cn)?', host)
            path_style = re.fullmatch(r's3(?:[.-][a-z0-9-]+)?\.amazonaws\.com(?:\.cn)?', host)
            if virtual:
                bucket, key = virtual.group(1), unquote(parsed.path.lstrip('/'))
            elif path_style:
                parts = unquote(parsed.path.lstrip('/')).split('/', 1)
                bucket, key = parts[0], parts[1] if len(parts) == 2 else ''
            else:
                raise InputSourceError('HTTPS input must be a standard AWS S3 URL')
            if parsed.query:
                raise InputSourceError('Use s3://bucket/key for signed or versioned links; this runner authenticates through the configured AWS credentials')
    else:
        if parsed.scheme and not (len(parsed.scheme) == 1 and value[1:3] in (':\\', ':/')):
            raise InputSourceError('Only local paths, s3:// URIs and AWS S3 HTTPS links are supported')
        return None
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', bucket):
        raise InputSourceError('Invalid S3 bucket name')
    if parsed.username or parsed.password or parsed.fragment:
        raise InputSourceError('S3 input must not contain user information or a URL fragment')
    return bucket, key


def aws_client(config_path: Path):
    """Use filled local settings or the standard boto3 environment/profile/role chain."""
    settings = json.loads(config_path.read_text(encoding="utf-8-sig")) if config_path.exists() else {}
    allowed = {'region_name', 'profile_name', 'aws_access_key_id', 'aws_secret_access_key', 'aws_session_token'}
    if not isinstance(settings, dict) or set(settings) - allowed:
        raise InputSourceError('AWS settings contain unsupported fields; use the credentials example')
    if any(not isinstance(value, str) for value in settings.values()):
        raise InputSourceError('AWS settings must contain string values')
    settings = {key: value.strip() for key, value in settings.items() if value.strip() and value.strip() not in PLACEHOLDERS}
    if bool(settings.get('aws_access_key_id')) != bool(settings.get('aws_secret_access_key')):
        raise InputSourceError('Fill both AWS access key and secret key, or leave both empty to use an AWS profile/environment/role')
    if settings.get('aws_session_token') and not settings.get('aws_access_key_id'):
        raise InputSourceError('A configured session token requires both access key and secret key')
    if settings.get('profile_name') and settings.get('aws_access_key_id'):
        raise InputSourceError('Choose either an AWS profile or explicit AWS keys')
    try:
        import boto3
    except ImportError as exc:
        raise InputSourceError('S3 inputs require boto3: pip install -r requirements.txt') from exc
    return boto3.Session(**settings).client('s3')


class InputSources:
    """Stage local/S3 inputs once per run, keeping original paths and file hashes."""

    def __init__(self, root: Path, session_root: Path, *, credentials_file=None, client=None):
        self.root = root.resolve()
        self.session_root = session_root
        cache_session = Path(session_root.parent.parent.name)/session_root.name if session_root.parent.name=='entries' else Path(session_root.name)
        self.cache = self.root / 'data' / '.input_cache' / cache_session
        self.credentials_file = Path(credentials_file or self.root / 'config/aws_credentials.local.json')
        self.client = client
        self.files = {}
        self.errors = []

    def _record(self, origin, path, **metadata):
        relative = path.resolve().relative_to(self.root).as_posix()
        if relative not in self.files:
            digest = hashlib.sha256()
            with path.open('rb') as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b''): digest.update(chunk)
            self.files[relative] = dict(origin=origin, local_path=relative, bytes=path.stat().st_size,
                sha256=digest.hexdigest(), **metadata)
        return relative

    def _destination(self, category, origin, parts):
        """Reject traversal and Windows-invalid keys instead of changing partition values."""
        for part in parts:
            if part in ('', '.', '..') or re.search(r'[<>:"\\|?*\x00-\x1f]', part) or part.endswith((' ', '.')) or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part):
                raise InputSourceError('An input filename cannot be safely staged on Windows; rename the object to a portable filename')
        path = self.cache / category / hashlib.sha256(origin.encode()).hexdigest()[:16] / Path(*parts)
        if not path.resolve().is_relative_to(self.cache.resolve()):
            raise InputSourceError('Input path would escape the cache directory')
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def resolve(self, values):
        if isinstance(values, str): values = [values]
        if not isinstance(values, (list, tuple)) or any(not isinstance(v, str) or not v.strip() for v in values):
            raise InputSourceError('Input paths must be a string or a list of nonempty strings')
        result = []
        for value in values:
            location = s3_location(value)
            if location:
                result.extend(self._s3(*location))
            else:
                result.extend(self._local(value))
        return list(dict.fromkeys(result))

    def _local(self, value):
        candidate = Path(value).expanduser()
        if not candidate.is_absolute(): candidate = self.root / candidate
        if candidate.is_dir():
            matches = sorted(p for p in candidate.rglob('*') if p.is_file() and p.suffix.lower() in SUPPORTED)
            if not matches: raise InputSourceError('Local folder contains no supported JSON or Parquet inputs')
        else:
            matches = sorted(Path(p).resolve() for p in glob(str(candidate), recursive=True) if Path(p).is_file())
        if not matches:
            # Existing ingestion diagnostics keep unresolved project-relative paths visible.
            if not Path(value).is_absolute() and candidate.resolve().is_relative_to(self.root): return [value]
            raise InputSourceError('Local input file or wildcard does not exist')
        result = []
        for source in matches:
            if source.suffix.lower() not in SUPPORTED:
                raise InputSourceError('Input files must be JSON or Parquet')
            path = source.resolve()
            if not path.is_relative_to(self.root):
                # Preserve directory hierarchy/hive partition labels for external local inputs.
                path = self._destination('local', str(source.parent), source.parts[1:])
                shutil.copy2(source, path)
            result.append(self._record(str(source), path, kind='local'))
        return result

    def _s3(self, bucket, key):
        if self.client is None:
            try: self.client = aws_client(self.credentials_file)
            except InputSourceError: raise
            except Exception as exc: raise InputSourceError(f'Cannot initialize AWS credentials ({type(exc).__name__}); check JSON format, AWS profile and temporary session token') from exc
        uri = f's3://{bucket}/{key}'
        wildcard = next((i for i,c in enumerate(key) if c in '*?['), None)
        exact = not key.endswith('/') and wildcard is None and PurePosixPath(key).suffix.lower() in SUPPORTED
        try:
            if exact:
                metadata = self.client.head_object(Bucket=bucket, Key=key)
                objects = [dict(Key=key, Size=metadata['ContentLength'], ETag=metadata.get('ETag'), LastModified=metadata.get('LastModified'))]
            else:
                prefix = key[:wildcard] if wildcard is not None else key.rstrip('/') + '/' if key else ''
                objects = [obj for page in self.client.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=prefix)
                    for obj in page.get('Contents', []) if not obj['Key'].endswith('/') and PurePosixPath(obj['Key']).suffix.lower() in SUPPORTED
                    and (wildcard is None or fnmatchcase(obj['Key'], key))]
            objects = sorted({obj['Key']: obj for obj in objects}.values(), key=lambda obj: obj['Key'])
            if not objects: raise InputSourceError(f'No JSON or Parquet objects found at {uri}')
            result = []
            for obj in objects:
                origin = f"s3://{bucket}/{obj['Key']}"
                existing = next((p for p, record in self.files.items() if record['origin'] == origin), None)
                if existing:
                    result.append(existing); continue
                path = self._destination('s3', bucket, obj['Key'].split('/'))
                temporary = path.with_name(path.name + '.download')
                try:
                    self.client.download_file(bucket, obj['Key'], str(temporary))
                    if temporary.stat().st_size != obj['Size']: raise InputSourceError('Downloaded object size differs from S3 metadata; rerun using a stable extraction snapshot')
                    temporary.replace(path)
                finally:
                    temporary.unlink(missing_ok=True)
                result.append(self._record(origin, path, kind='s3', etag=obj.get('ETag'),
                    last_modified=str(obj.get('LastModified') or ''), bucket=bucket, key=obj['Key']))
            return result
        except InputSourceError: raise
        except Exception as exc:
            code = getattr(exc, 'response', {}).get('Error', {}).get('Code', type(exc).__name__)
            advice = {
                'NoCredentialsError': 'No usable credentials found: fill the local AWS settings, configure an AWS profile, or set AWS credential environment variables',
                'ExpiredToken': 'Temporary AWS credentials expired: refresh access key, secret key and session token together',
                'ExpiredTokenException': 'Temporary AWS credentials expired: refresh all three credential fields together',
                'InvalidAccessKeyId': 'AWS rejected the access key: check the configured account credentials',
                'SignatureDoesNotMatch': 'AWS signature mismatch: check secret key, session token, region and machine clock',
                'AccessDenied': 'AWS denied access: the role/user needs GetObject for files and ListBucket for folder discovery; encrypted objects may require KMS decrypt permission',
                '403': 'AWS denied access: verify the bucket policy, IAM read/list permissions and account credentials',
                '404': 'S3 object not found: verify the bucket and exact case-sensitive object key',
                'NoSuchBucket': 'S3 bucket not found: verify bucket name and region',
                'NoSuchKey': 'S3 object not found: verify the exact case-sensitive object key',
            }.get(str(code), 'Check credentials, read/list permissions, bucket, key and region')
            # No exception payloads or URL query credentials in terminal/report evidence.
            raise InputSourceError(f'S3 input could not be read ({code}): {advice}') from exc

    def prepare(self, stage_runs, *, selected_stage=None, connected=False, start_stage="final_action", generate_outputs=None):
        """Resolve enabled entries including role-specific and downstream candidate paths."""
        configured = deepcopy(stage_runs)
        try:
            for stage, settings in configured.items():
                if not settings.get('enabled', True) or selected_stage and stage != selected_stage or connected and stage != start_stage: continue
                for list_name in ('single_files', 'folder_paths'):
                    for item in settings.get(list_name, []):
                        if not item.get('enabled', True): continue
                        for role in ('source', 'actual', 'expected', 'dropped'):
                            if item.get(role): item[role] = self.resolve(item[role])
                        for target, values in (item.get('pipeline_outputs', {}) if generate_outputs is not True else {}).items():
                            item['pipeline_outputs'][target] = self.resolve(values)
            return configured
        except InputSourceError as exc:
            self.errors.append(str(exc))
            raise
        except OSError as exc:
            message = 'Cannot read or stage local input files; check file permissions, free disk space and cache path'
            self.errors.append(message)
            raise InputSourceError(message) from exc
        finally:
            self.write_inventory()

    def write_inventory(self):
        self.session_root.mkdir(parents=True, exist_ok=True)
        files = sorted(self.files.values(), key=lambda item: item['local_path'])
        payload = dict(generated=datetime.now(timezone.utc).isoformat(), resolved_files=len(files), files=files, errors=self.errors)
        (self.session_root / 'input_sources.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
        esc = html.escape
        rows = ''.join(f'<tr><td>{n}</td><td>{esc(r["origin"])}</td><td>{esc(r["local_path"])}</td><td>{r["bytes"]}</td><td>{esc(r["sha256"])}</td></tr>' for n,r in enumerate(files,1))
        errors = ''.join('<p>'+esc(message)+'</p>' for message in self.errors)
        (self.session_root / 'input_sources.html').write_text('<!doctype html><meta charset="utf-8"><title>MEDPAR input sources</title><style>body{font:15px system-ui;margin:32px;color:#172033}table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #ddd;overflow-wrap:anywhere}summary{cursor:pointer}</style><h1>Input source verification</h1>'+f'<p>Unique resolved files: {len(files)}. This confirms downloaded/local file identity, not business-rule acceptance.</p>'+errors+'<details><summary>Original sources, local files and fingerprints</summary><table><tr><th>No.</th><th>Original source</th><th>File used by validation</th><th>Bytes</th><th>SHA-256</th></tr>'+rows+'</table></details><p><a href="master/index.html">Master report</a> · <a href="input_sources.json">JSON evidence</a></p>', encoding='utf-8')
