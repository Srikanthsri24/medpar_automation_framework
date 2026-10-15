import threading
import pytest
from medpar_qa.progress import Progress,activity


def test_known_total_reports_percentage_and_remaining(capsys):
    p=Progress('Download',100,'bytes',interval=0)
    p.advance(25);p.advance(1000);p.finish()
    text=capsys.readouterr().out
    assert '25/100 bytes (25.0%); 75 remaining' in text
    assert '100/100 bytes (100.0%); 0 remaining' in text


def test_unknown_total_does_not_invent_percentage(capsys):
    p=Progress('JSON scan',unit='rows',interval=0);p.update(2000);p.finish()
    text=capsys.readouterr().out
    assert '2,000 rows' in text and '%' not in text


def test_activity_heartbeat_and_failure_preserve_exception(monkeypatch,capsys):
    import medpar_qa.progress as log
    heartbeat=threading.Event();original=log.emit
    def observe(message,**kwargs):
        original(message,**kwargs)
        if str(message).startswith('WORKING:'):heartbeat.set()
    monkeypatch.setattr(log,'HEARTBEAT_SECONDS',.01)
    monkeypatch.setattr(log,'emit',observe)
    with pytest.raises(ValueError,match='original failure'):
        with activity('Reference comparison'):
            assert heartbeat.wait(1)
            raise ValueError('original failure')
    text=capsys.readouterr().out
    assert 'START: Reference comparison' in text
    assert 'WORKING:' in text and 'FAILED: Reference comparison' in text
    assert not log._tasks


def test_real_download_callback_is_connected(tmp_path,capsys):
    from medpar_qa.ingestion.input_sources import InputSources
    class Client:
        called=False
        def head_object(self,**kwargs):return {'ContentLength':len(b'[]'),'ETag':'v1'}
        def download_file(self,bucket,key,filename,Callback=None):
            assert callable(Callback)
            self.called=True
            Callback(1);Callback(1)
            from pathlib import Path
            Path(filename).write_bytes(b'[]')
    client=Client();source=InputSources(tmp_path,tmp_path/'reports/run',client=client)
    source.resolve(['s3://medpar-demo-bucket/original.json'])
    text=capsys.readouterr().out
    assert client.called and '100.0%' in text and '0 remaining' in text
