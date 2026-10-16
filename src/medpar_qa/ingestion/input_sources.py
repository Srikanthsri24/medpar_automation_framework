"""Resolve runner inputs into local files with auditable, credential-free provenance."""
from __future__ import annotations
from medpar_qa.progress import tracked, emit, Progress

from concurrent.futures import ThreadPoolExecutor
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

    def __init__(self, root: Path, session_root: Path, *, credentials_file=None, client=None, s3_read_mode="download", row_selection=None, s3_workers=8):
        if type(s3_workers) is not int or not 1 <= s3_workers <= 32:
            raise InputSourceError("s3_workers must be an integer from 1 to 32")
        self.s3_workers = s3_workers
        self.root = root.resolve()
        self.session_root = session_root
        cache_session = Path(session_root.parent.parent.name)/session_root.name if session_root.parent.name=='entries' else Path(session_root.name)
        self.cache = self.root / 'data' / '.input_cache' / cache_session
        self.credentials_file = Path(credentials_file or self.root / 'config/aws_credentials.local.json')
        self.client = client
        self.files = {}
        self.errors = []
        if s3_read_mode not in ("download","sample_parquet"):raise InputSourceError("s3_read_mode must be download or sample_parquet")
        self.s3_read_mode=s3_read_mode
        self.row_selection=row_selection or {}
        self._sample_source=False

    def _record(self, origin, path, **metadata):
        relative = path.resolve().relative_to(self.root).as_posix()
        if relative not in self.files:
            emit(f'Verifying cached file and SHA-256: {path}')
            hashed=Progress('Cache bytes hashed',path.stat().st_size,'bytes')
            digest = hashlib.sha256()
            with path.open('rb') as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                    digest.update(chunk);hashed.advance(len(chunk))
            hashed.finish()
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

    def resolve(self, values, *, sample_source=False):
        previous=self._sample_source
        self._sample_source=sample_source
        try:return self._resolve(values)
        finally:self._sample_source=previous

    def _resolve(self, values):
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
                emit(f'Copying external local input into run cache: {source} ({source.stat().st_size:,} bytes)')
                shutil.copy2(source, path)
            result.append(self._record(str(source), path, kind='local'))
        return result

    def _download_cached(self, bucket, obj, destination, kwargs):
        """Reuse complete ETag-pinned objects; verify local bytes before reuse.

        Partial Parquet samples are deliberately excluded from this shared cache.
        Corrupt cache entries are replaced with a fresh download.
        """
        etag = obj.get('ETag')
        if not etag:
            return self.client.download_file(bucket, obj['Key'], str(destination), **kwargs)
        identity = json.dumps([bucket, obj['Key'], etag, obj['Size'], str(obj.get('LastModified') or '')])
        cache_dir = self.root/'data/.input_cache/shared'/hashlib.sha256(identity.encode()).hexdigest()
        payload, manifest = cache_dir/'object.bin', cache_dir/'snapshot.json'
        def digest(path):
            value = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024*1024), b''):
                    value.update(block)
            return value.hexdigest()
        if payload.exists() and manifest.exists():
            try:
                saved = json.loads(manifest.read_text(encoding='utf-8'))
                valid = payload.stat().st_size == obj['Size'] and digest(payload) == saved['sha256']
            except (OSError, ValueError, KeyError):
                valid = False
            if valid:
                emit(f"Reusing verified S3 cache: s3://{bucket}/{obj['Key']}; no object download")
                shutil.copyfile(payload, destination)
                return
        self.client.download_file(bucket, obj['Key'], str(destination), **kwargs)
        if destination.stat().st_size != obj['Size']:
            raise InputSourceError('Downloaded object size differs from S3 metadata')
        cache_dir.mkdir(parents=True, exist_ok=True)
        # Separate temporary names keep simultaneous processes from sharing partial bytes.
        import tempfile
        with tempfile.NamedTemporaryFile(dir=cache_dir, delete=False) as handle:
            temporary = Path(handle.name)
        try:
            shutil.copyfile(destination, temporary)
            fingerprint = digest(temporary)
            temporary.replace(payload)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=cache_dir, delete=False) as handle:
                json.dump({'sha256': fingerprint, 'etag': etag, 'bytes': obj['Size']}, handle)
                metadata_tmp = Path(handle.name)
            metadata_tmp.replace(manifest)
        finally:
            temporary.unlink(missing_ok=True)

    def _s3(self, bucket, key):
        if self.client is None:
            try: self.client = aws_client(self.credentials_file)
            except InputSourceError: raise
            except Exception as exc: raise InputSourceError(f'Cannot initialize AWS credentials ({type(exc).__name__}); check JSON format, AWS profile and temporary session token') from exc
        uri = f's3://{bucket}/{key}'
        emit(f'Resolving S3 input: {uri}; checking object or listing prefix')
        wildcard = next((i for i,c in enumerate(key) if c in '*?['), None)
        exact = bool(key) and not key.endswith('/') and wildcard is None
        try:
            if exact:
                try:
                    metadata = self.client.head_object(Bucket=bucket, Key=key)
                    objects = [dict(Key=key, Size=metadata['ContentLength'], ETag=metadata.get('ETag'), LastModified=metadata.get('LastModified'))]
                except Exception as exc:
                    code=str(getattr(exc,'response',{}).get('Error',{}).get('Code',''))
                    if code not in ('404','NoSuchKey','NotFound'):raise
                    exact=False
            if not exact:
                prefix = key[:wildcard] if wildcard is not None else key.rstrip('/') + '/' if key else ''
                def pages():
                    for page_number,page in enumerate(self.client.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=prefix),1):
                        emit(f'S3 listing page {page_number}: s3://{bucket}/{prefix}; {len(page.get("Contents",[]))} keys returned on this page')
                        yield page
                objects = [obj for page in pages()
                    for obj in page.get('Contents', []) if not obj['Key'].endswith('/') and PurePosixPath(obj['Key']).name not in ('_SUCCESS','_metadata','_common_metadata')
                    and not PurePosixPath(obj['Key']).name.startswith(('_started_','_committed_'))
                    and PurePosixPath(obj['Key']).suffix.lower() not in ('.txt','.md','.log','.crc')
                    and (wildcard is None or fnmatchcase(obj['Key'], key))]
            emit(f'S3 discovery: {len(objects)} object(s) at {uri}')
            objects = sorted({obj['Key']: obj for obj in objects}.values(), key=lambda obj: obj['Key'])
            if not objects: raise InputSourceError(f'No JSON or Parquet objects found at {uri}')
            result = []
            objects_progress=Progress('S3 objects prepared',len(objects),'objects')
            def prepare_object(obj):
                emit(f"S3 object: s3://{bucket}/{obj['Key']} ({obj['Size']:,} bytes)")
                origin = f"s3://{bucket}/{obj['Key']}"
                existing = next((p for p, record in self.files.copy().items() if record['origin'] == origin and (not record.get('access_mode')=='s3_parquet_sample' or self._sample_source)), None)
                if existing:
                    return existing
                needs_detection=PurePosixPath(obj['Key']).suffix.lower() not in SUPPORTED
                path = self._destination('s3', origin if needs_detection else bucket, obj['Key'].split('/'))
                eligible=(self.s3_read_mode=='sample_parquet' and self._sample_source and self.row_selection.get('mode')=='first_n_per_file' and self.row_selection.get('include_related_records',True) is False and type(self.row_selection.get('limit')) is int and self.row_selection['limit']>0 and hasattr(self.client,'get_object') and bool(obj.get('ETag')) and PurePosixPath(obj['Key']).suffix.lower()!='.json')
                if eligible:
                    from .s3_sampling import stage_parquet_sample
                    sample_path=path.with_name(path.name+'.selected.parquet')
                    sampled=stage_parquet_sample(self.client,bucket,obj['Key'],obj['Size'],obj.get('ETag'),sample_path,self.row_selection['limit'],cache_directory=self.root/'data/.input_cache/samples')
                    if sampled is not None:
                        resolved = self._record(origin,sample_path,kind='s3',bucket=bucket,key=obj['Key'],etag=obj.get('ETag'),detected_format='parquet',**sampled)
                        print(f"S3 Parquet sample: {self.row_selection['limit']} requested; {sampled['cached_rows']} cached / {sampled['source_total_rows']} source rows; {sampled['bytes_transferred']} bytes transferred / {sampled['source_bytes']} object bytes",flush=True)
                        return resolved
                    if PurePosixPath(obj['Key']).suffix.lower()=='.parquet':raise InputSourceError('Parquet object has an invalid header')
                temporary = path.with_name(path.name + '.download')
                try:
                    import inspect
                    transfer=Progress('Downloading '+origin,obj['Size'],'bytes')
                    parameters=inspect.signature(self.client.download_file).parameters
                    callback_supported='Callback' in parameters or any(v.kind==inspect.Parameter.VAR_KEYWORD for v in parameters.values())
                    kwargs={'Callback':transfer.advance} if callback_supported else {}
                    self._download_cached(bucket, obj, temporary, kwargs)
                    transfer.finish()
                    if temporary.stat().st_size != obj['Size']: raise InputSourceError('Downloaded object size differs from S3 metadata; rerun using a stable extraction snapshot')
                    detected=None
                    if needs_detection:
                        with temporary.open('rb') as handle:
                            sample=handle.read(65536)
                            handle.seek(max(0,temporary.stat().st_size-4));tail=handle.read(4)
                        if sample[:4]==b'PAR1' and tail==b'PAR1':detected='parquet'
                        elif sample.removeprefix(b'\xef\xbb\xbf').lstrip().startswith((b'{',b'[')):detected='json'
                        else:raise InputSourceError(f'Object content is not recognizable JSON or Parquet: {origin}')
                        path=path.with_name(path.name+'.'+detected)
                    temporary.replace(path)
                finally:
                    temporary.unlink(missing_ok=True)
                return self._record(origin, path, kind='s3', etag=obj.get('ETag'),
                    last_modified=str(obj.get('LastModified') or ''), bucket=bucket, key=obj['Key'],
                    detected_format=detected, format_detection='content' if needs_detection else 'extension')
            # map preserves sorted discovery order; each worker owns a distinct object.
            # Iteration raises any worker error, so a partial folder is never accepted.
            with ThreadPoolExecutor(max_workers=self.s3_workers, thread_name_prefix='medpar-s3') as pool:
                for object_number, resolved in enumerate(pool.map(prepare_object, objects), 1):
                    result.append(resolved)
                    objects_progress.update(object_number, force=True)
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
                'PreconditionFailed': 'The S3 object changed during the range read; retry against a stable extraction snapshot',
                '412': 'The S3 object changed during the range read; retry against a stable extraction snapshot',
            }.get(str(code), 'Check credentials, read/list permissions, bucket, key and region')
            # No exception payloads or URL query credentials in terminal/report evidence.
            raise InputSourceError(f'S3 input could not be read ({code}): {advice}') from exc

    @tracked('Resolve and prepare local/S3 source and reference inputs')
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
                            if item.get(role):
                                emit(f'Preparing {stage} dataset {role}: {len(item[role]) if not isinstance(item[role],str) else 1} configured path(s)')
                                item[role] = self.resolve(item[role],sample_source=role=="source")
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
        rows = ''.join(f'<tr><td>{n}</td><td>{esc(r["origin"])}</td><td>{esc(r["local_path"])}</td><td>{r["bytes"]}</td><td>{esc(r["sha256"])}</td><td>{esc(r.get("access_mode","Complete local file or download"))}<br>{esc(str(r.get("cached_rows","All")))} cached rows / {esc(str(r.get("source_total_rows","Counted during validation")))} source rows<br>{esc(r.get("hash_scope","Complete cached file"))}</td></tr>' for n,r in enumerate(files,1))
        errors = ''.join('<p>'+esc(message)+'</p>' for message in self.errors)
        (self.session_root / 'input_sources.html').write_text('<!doctype html><meta charset="utf-8"><title>MEDPAR input sources</title><style>body{font:15px system-ui;margin:32px;color:#172033}table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #ddd;overflow-wrap:anywhere}summary{cursor:pointer}</style><h1>Input source verification</h1>'+f'<p>Unique resolved files: {len(files)}. This confirms downloaded/local file identity, not business-rule acceptance.</p>'+errors+'<details><summary>Original sources, local files and fingerprints</summary><table><tr><th>No.</th><th>Original source</th><th>File used by validation</th><th>Cached bytes</th><th>Cached file SHA-256</th><th>Read method and scope</th></tr>'+rows+'</table></details><p><a href="master/index.html">Master report</a> · <a href="input_sources.json">JSON evidence</a></p>', encoding='utf-8')
