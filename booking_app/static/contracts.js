// Public DTO allowlists; personal fields never enter shared schedule records.
(() => {
  "use strict";
  const keys = (v,names) => v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).sort().join(",") === names.split(",").sort().join(",");
  const id = v => Number.isSafeInteger(v) && v > 0;
  const integer = Number.isSafeInteger;
  const text = v => typeof v === "string";
  const nullable = (v,check) => v === null || check(v);
  const pair = (epoch,local) => integer(epoch) && text(local) && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+08:00$/.test(local) && Date.parse(local)/1000 === epoch;
  const room = v => keys(v,"id,name,location,capacity") && id(v.id) && id(v.capacity) && text(v.name) && text(v.location);
  function supervisor(v) {
    return ["teacher","application","admin","legacy"].includes(v.supervisor_source) &&
      (["teacher","application"].includes(v.supervisor_source) ? text(v.supervisor_display_name) : v.supervisor_display_name === null);
  }
  function bookingOrigin(v) {
    if (v.supervisor_source === "application") return id(v.supervisor_id) && v.owner_id !== v.supervisor_id &&
      id(v.application_id) && integer(v.approved_at) && v.approved_by === v.supervisor_id;
    const directOrigin = v.application_id === null
      ? [v.approved_at,v.approved_by].every(x => x === null)
      : id(v.application_id) && integer(v.approved_at) && v.approved_by === v.owner_id;
    return directOrigin && (v.supervisor_source === "teacher" ? id(v.supervisor_id) && v.supervisor_id === v.owner_id : v.supervisor_id === null);
  }
  function booking(v) {
    return keys(v,"id,room,title,purpose,attendees,owner_id,owner_display_name,start_at,start_local,end_at,end_local,status,created_at,created_local,cancelled_at,cancelled_local,cancelled_by_id,cancelled_by_display_name,cancel_reason,supervisor_id,supervisor_display_name,supervisor_source,application_id,approved_at,approved_by") &&
      [v.id,v.attendees,v.owner_id].every(id) && room(v.room) && [v.title,v.purpose,v.owner_display_name].every(text) &&
      pair(v.start_at,v.start_local) && pair(v.end_at,v.end_local) && v.start_at < v.end_at && pair(v.created_at,v.created_local) &&
      ["pending","in_progress","ended","cancelled"].includes(v.status) && supervisor(v) &&
      bookingOrigin(v) &&
      (v.status === "cancelled" ? pair(v.cancelled_at,v.cancelled_local) && id(v.cancelled_by_id) && text(v.cancelled_by_display_name) && nullable(v.cancel_reason,text) :
        [v.cancelled_at,v.cancelled_local,v.cancelled_by_id,v.cancelled_by_display_name,v.cancel_reason].every(x => x === null));
  }
  function application(v) {
    const names="id,owner_id,owner_display_name,supervisor_id,supervisor_display_name,room_id,title,purpose,attendees,start_at,end_at,weeks,status,created_at,decided_at,decided_by,decision_reason,room,start_local,end_local,expired,reservation_id";
    if (!(keys(v,names) || keys(v,names+",occurrences"))) return false;
    if (!(integer(v.weeks) && v.weeks >= 1 && v.weeks <= 8 && (v.weeks === 1) === !Object.hasOwn(v,"occurrences"))) return false;
    if (v.weeks > 1 && (!Array.isArray(v.occurrences) || v.occurrences.length !== v.weeks || !v.occurrences.every((item,index) =>
      keys(item,"occurrence,start_at,end_at,start_local,end_local,reservation_id,status") && item.occurrence === index+1 &&
      pair(item.start_at,item.start_local) && pair(item.end_at,item.end_local) &&
      item.start_at === v.start_at+index*604800 && item.end_at === v.end_at+index*604800 &&
      (v.status === "approved" ? id(item.reservation_id) && ["pending","in_progress","ended","cancelled"].includes(item.status) : item.reservation_id === null && item.status === null)))) return false;
    return [v.id,v.owner_id,v.supervisor_id,v.room_id,v.attendees].every(id) && room(v.room) && v.room.id === v.room_id &&
      [v.owner_display_name,v.supervisor_display_name,v.title,v.purpose].every(text) && integer(v.created_at) &&
      pair(v.start_at,v.start_local) && pair(v.end_at,v.end_local) && v.end_at > v.start_at && typeof v.expired === "boolean" &&
      ["awaiting_approval","approved","rejected","withdrawn"].includes(v.status) && nullable(v.decision_reason,text) &&
      (v.status === "awaiting_approval" ? [v.decided_at,v.decided_by,v.decision_reason,v.reservation_id].every(x => x === null) :
        integer(v.decided_at) && id(v.decided_by) && (v.status === "approved" ? id(v.reservation_id) : v.reservation_id === null)) &&
      (v.status !== "rejected" || text(v.decision_reason) && v.decision_reason.trim().length > 0);
  }
  function schedule(v) {
    if (!keys(v,"kind,record")) return false;
    const r=v.record, common="room_id,room_name,start_at,start_local,end_at,end_local,status";
    return ["booking","block"].includes(v.kind) && keys(r,common+(v.kind === "booking" ? ",title,owner_display_name,supervisor_display_name,supervisor_source" : ",id,reason")) &&
      id(r.room_id) && text(r.room_name) && pair(r.start_at,r.start_local) && pair(r.end_at,r.end_local) &&
      ["pending","in_progress","ended"].includes(r.status) && (v.kind === "booking" ? text(r.title) && text(r.owner_display_name) && supervisor(r) : id(r.id) && text(r.reason));
  }
  window.BookingContracts = {booking,application,schedule,room};
})();
