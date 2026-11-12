"""Architecture 6.3 exact external keys; test data only."""
from tests.history_fixtures import FULL_KEYS as BOOKING_KEYS
BLOCK_KEYS = {'id','room','creator_id','creator_display_name','reason','start_at','start_local','end_at','end_local',
              'status','created_at','created_local','revoked_at','revoked_local','revoked_by_id','revoked_by_display_name','revoke_reason'}
BLOCK_SNAPSHOT_KEYS = {'id','room_id','creator_id','reason','start_at','end_at','created_at','revoked_at','revoked_by_id','revoke_reason'}
