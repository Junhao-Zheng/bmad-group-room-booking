"""Targeted evidence retention when cancellation HTTP workers fail."""
from concurrent.futures import Future
import json
from pathlib import Path
import tempfile
import unittest

from booking_app import db
from scripts import verify_member_cancel_http as runner


class MemberCancelHttpRunnerTests(unittest.TestCase):
    def test_first_worker_failure_drains_all_outcomes_and_saves_storage_without_exception_text(self):
        consumed=[]
        class ObservedFuture(Future):
            def __init__(self,index): super().__init__(); self.index=index
            def result(self,timeout=None):
                consumed.append(self.index)
                return super().result(timeout)
        class ResponseFailure(Exception): status=503
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory);database=output/'booking.sqlite3'
            db.initialize_database(database)
            futures=[ObservedFuture(i) for i in range(3)]
            futures[0].set_exception(RuntimeError('password=private csrf_token=private cookie=private'))
            futures[1].set_result(dict(index=1,http_status=200,response={'ok':True,'data':{'id':1}},duration_ms=1))
            futures[2].set_exception(ResponseFailure('Authorization: private-secret'))
            responses=runner.collect_race_responses(futures,output,database)
            self.assertEqual(consumed,[0,1,2])
            self.assertEqual(responses[0],dict(index=0,http_status=None,error_type='RuntimeError'))
            self.assertEqual(responses[1]['http_status'],200)
            self.assertEqual(responses[2],dict(index=2,http_status=503,error_type='ResponseFailure'))
            raw=(output/'concurrent-responses.jsonl').read_text()
            self.assertEqual([json.loads(line) for line in raw.splitlines()],responses)
            self.assertNotIn('private',raw)
            self.assertEqual(json.loads((output/'after-race.json').read_text()),runner.facts(database))
            self.assertFalse(all(row['http_status']==200 for row in responses))


if __name__=='__main__': unittest.main()
