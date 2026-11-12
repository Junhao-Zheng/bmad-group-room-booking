// Test oracle for the user-visible fields in the complete management lists.
const assert=require('node:assert/strict');
function expectedRows(records,kind){
  const label={pending:'待开始',in_progress:'进行中',ended:'已结束',cancelled:'已取消',revoked:'已撤销'};
  const stamp=value=>value.slice(0,10)+' '+value.slice(11,19);
  return records.map(row=>{
    const booking=kind==='bookings',terminal=booking?'cancelled':'revoked';
    const pairs=[['会议室',`${row.room.id} · ${row.room.name} · ${row.room.location} · 容量 ${row.room.capacity} 人`],
      ['时段（北京时间）',`${stamp(row.start_local)} 至 ${stamp(row.end_local)}`]];
    if(booking)pairs.push(['活动名称',row.title],['用途',row.purpose],['预计人数',`${row.attendees} 人`],['预约人',`${row.owner_id} · ${row.owner_display_name}`]);
    else pairs.push(['停用原因',row.reason],['创建者',`${row.creator_id} · ${row.creator_display_name}`]);
    pairs.push(['创建时间（北京时间）',stamp(row.created_local)]);
    let details=booking?'未取消':'未撤销';
    if(row[terminal+'_at']!==null)details=`${stamp(row[terminal+'_local'])}（北京时间） · 操作者 ${row[terminal+'_by_id']} · ${row[terminal+'_by_display_name']}\n原因：${row[booking?'cancel_reason':'revoke_reason']??'本人取消，无原因'}`;
    pairs.push([booking?'取消信息':'撤销信息',details]);
    return {title:`${booking?'预约':'停用'} ${row.id} · ${label[row.status]}`,pairs};
  });
}
function assertRendered(actual,records,kind){assert.deepEqual(actual,expectedRows(records,kind));}
module.exports={expectedRows,assertRendered};
