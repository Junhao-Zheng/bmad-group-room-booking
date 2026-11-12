const {test}=require('node:test'),assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs'),os=require('node:os');
const driverPath=path.resolve(__dirname,'../scripts/verify_room_management_browser.cjs');
const {safeDiagnostic,writeFailure}=require(driverPath);

test('browser assertion diagnostics retain only own-script coordinates and controlled stage/type',()=>{
  const secret='SYNTHETIC_PRIVATE_password_cookie_csrf';
  const error=new assert.AssertionError({actual:secret,expected:'other',operator:'strictEqual'});
  error.stack=`AssertionError: ${secret}\n    at assert (${driverPath}:91:7)\n    at elsewhere (/private/${secret}:4:8)`;
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'room-diagnostic-'));
  try{
    const diagnostic=writeFailure(error,output,'capacity');
    assert.deepEqual(diagnostic,{stage:'capacity',error_type:'AssertionError',source:{file:'scripts/verify_room_management_browser.cjs',line:91,column:7}});
    const serialized=fs.readFileSync(path.join(output,'failure-diagnostics.json'),'utf8');
    assert.equal(serialized.includes(secret),false);assert.equal(serialized.includes('actual'),false);assert.equal(serialized.includes('expected'),false);
  }finally{fs.rmSync(output,{recursive:true});}
});
test('unknown errors, foreign stack frames and uncontrolled stages cannot expose text',()=>{
  assert.deepEqual(safeDiagnostic({name:'PRIVATE',message:'PRIVATE',stack:'PRIVATE\n    at /private/file.js:2:3'},'PRIVATE'),
    {stage:'startup',error_type:'Error',source:null});
});
