const {test}=require('node:test'),assert=require('node:assert/strict');
const {safeDiagnostic}=require('../scripts/verify_block_revoke_browser.cjs');
test('driver diagnostics never expose error messages, fill secrets or arbitrary names',()=>{
  const secret='SENTINEL_PRIVATE_FILL_SECRET';
  const error=new Error(`locator.fill ${secret}`);
  error.stack=`Error: ${secret}\n    at fill (/private/${secret}:10:20)\n    at main (${require.resolve('../scripts/verify_block_revoke_browser.cjs')}:80:12)`;
  assert.deepEqual(safeDiagnostic(error,'login'),{stage:'login',error_type:'Error',source:{file:'scripts/verify_block_revoke_browser.cjs',line:80,column:12}});
  error.name=secret;assert.equal(safeDiagnostic(error,secret).error_type,'Error');assert.equal(safeDiagnostic(error,secret).stage,'startup');
  assert.equal(JSON.stringify(safeDiagnostic(error,secret)).includes(secret),false);
});
