const form = document.querySelector('#form'), result = document.querySelector('#result'), loading = document.querySelector('#loading'), submit = document.querySelector('#submit');
const esc = s => String(s ?? 'Not stated').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[c]));

form.addEventListener('submit', async event => {
  event.preventDefault(); result.hidden = true; loading.hidden = false; submit.disabled = true;
  try {
    const token = localStorage.getItem('token');
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    
    const response = await fetch('/api/reconcile', { 
      method: 'POST', 
      headers: headers,
      body: new FormData(form) 
    });
    const data = await response.json(); 
    if (!response.ok) throw Error(data.detail || 'Could not reconcile evidence.');
    
    // Auto-save comparison to PostgreSQL database via History microservice if authenticated
    if (token) {
      try {
        await fetch('/api/history/save', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({
            id: data.id,
            image_url: data.image_url,
            audio_url: data.audio_url,
            transcript: data.transcript,
            document_data: data.document,
            result_data: data.result
          })
        });
      } catch (saveErr) {
        console.error('Failed to auto-save history record:', saveErr);
      }
    }
    
    render(data);
  } catch (err) {
    result.innerHTML = `<article class="error"><b>No decision issued</b><p>${esc(err.message)}</p><small>Sakshi did not invent a payment recommendation.</small></article>`; result.hidden = false;
  } finally { loading.hidden = true; submit.disabled = false; }
});

document.querySelector('#evaluate').addEventListener('click', async () => {
  const target = document.querySelector('#evaluation'); target.textContent = 'Running safety evaluation…';
  try { const data = await (await fetch('/api/evaluate')).json(); target.innerHTML = `<b>${data.passed}/${data.case_count} cases passed · ${data.decision_accuracy}% accuracy · ${data.unsafe_approvals} unsafe approvals</b>`; }
  catch { target.textContent = 'Evaluation unavailable. Check the local server.'; }
});

function render(data) {
  const x = data.result, conflicts = x.conflicts || [], evidence = x.provenance || [], items = (data.document.items || []).map(i => `<li><b>${esc(i.name)}</b><span>${esc(i.quantity)} ${esc(i.unit)} · ${Math.round(Number(i.confidence || 0) * 100)}% document readability</span></li>`).join('');
  const rows = evidence.map(e => `<li><b>${esc(e.field)}${e.item ? ` — ${esc(e.item)}` : ''}</b><span>${esc(e.value)} · ${esc(e.source)}${e.timestamp ? ` · ${esc(e.timestamp)}` : ''} · ${esc(e.quality)}</span></li>`).join('');
  const quality = x.evidence_quality || { level: 'LOW', score: 0, factors: [] };
  const timing = data.observability?.timings_ms || {};
  result.innerHTML = `<article class="verdict ${esc(x.decision)}"><div><p class="eyebrow">RECONCILIATION #${esc(data.id)}</p><h2>${esc(x.decision).replaceAll('_', ' ')}</h2><p>${esc(x.reasoning_summary)}</p><small>Final state enforced by: ${esc(x.decision_basis)}</small></div><strong>${esc(quality.level)}<small>Evidence Quality · ${esc(quality.score)}/100</small></strong></article>
  <div class="results"><article class="card"><p class="eyebrow">DOCUMENT CLAIM</p><h3>${esc(data.document.supplier?.value)} · ${esc(data.document.date?.value)}</h3><ul>${items || '<li>No readable items</li>'}</ul></article><article class="card"><p class="eyebrow">VOICE CLAIM</p><blockquote>“${esc(data.transcript)}”</blockquote></article></div>
  <article class="card conflicts"><p class="eyebrow">${conflicts.length ? 'CONFLICTS FOUND' : 'EVIDENCE ALIGNMENT'}</p>${conflicts.length ? conflicts.map(c => `<div class="conflict"><b>${esc(c.field)}</b><p>Challan: ${esc(c.document_claim)}<br>Voice note: ${esc(c.voice_claim)}</p><small>${esc(c.why)}</small></div>`).join('') : '<p>No material conflict was identified. Human review remains required before payment.</p>'}<div class="question"><b>Ask next</b><p>${esc(x.review_question)}</p></div></article>
  <div class="results"><article class="card"><p class="eyebrow">EVIDENCE TRAIL</p><ul>${rows || '<li>No evidence trail available</li>'}</ul></article><article class="card"><p class="eyebrow">OBSERVABILITY</p><p>Vision: ${esc(timing.vision_ms ?? '—')} ms<br>Speech: ${esc(timing.transcription_ms ?? '—')} ms<br>Reconciliation: ${esc(timing.reconciliation_ms ?? '—')} ms<br>Total: ${esc(data.observability?.total_ms ?? '—')} ms</p><label class="voice-language">Voice language<select id="voice-language"><option value="hi-IN">Hindi / Hinglish</option><option value="te-IN">Telugu</option><option value="ml-IN">Malayalam</option><option value="kn-IN">Kannada</option><option value="en-IN">English</option></select></label><label class="voice-language">Voice<select id="voice-choice"></select></label><div id="voice-warning" style="color: #b73c2f; font-size: 12px; margin-top: -6px; margin-bottom: 12px; display: none; line-height: 1.4;"></div><label class="voice-language">Speaking style<select id="voice-rate"><option value="0.88">Calm and clear</option><option value="0.96">Natural</option><option value="1.05">Faster</option></select></label><button class="secondary" id="listen" type="button">Listen to review</button><button class="secondary" id="packet" type="button">Download review packet</button><div id="translation-box" style="margin-top: 15px; font-size: 13px; font-style: italic; color: #53645f; display: none; line-height: 1.4;"></div></article></div>`;
  document.querySelector('#packet').addEventListener('click', () => downloadPacket(data));
  document.querySelector('#listen').addEventListener('click', () => speakReview(data));
  document.querySelector('#voice-language').addEventListener('change', updateVoiceOptions);
  
  const onVoicesChanged = () => {
    populateLanguages();
    updateVoiceOptions();
  };
  onVoicesChanged();
  if ('speechSynthesis' in window) {
    window.speechSynthesis.onvoiceschanged = onVoicesChanged;
  }
  
  result.hidden = false; result.scrollIntoView({ behavior: 'smooth' });
}

async function downloadPacket(data) {
  const response = await fetch('/api/review-packet', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
  const blob = await response.blob(), link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `sakshi-review-${data.id}.json`; link.click(); URL.revokeObjectURL(link.href);
}

async function speakReview(data) {
  if (!('speechSynthesis' in window)) { alert('Voice playback is not supported in this browser.'); return; }
  window.speechSynthesis.cancel();
  const result = data.result, conflicts = result.conflicts || [];
  const language = document.querySelector('#voice-language').value;
  const listenBtn = document.querySelector('#listen');
  
  let message = '';
  const langPrefix = language.split('-')[0].toLowerCase();
  const isLatn = language.toLowerCase().includes('latn');
  const hardcodedKeys = ['hi-IN', 'te-IN', 'ml-IN', 'kn-IN', 'en-IN'];
  const matchedKey = isLatn ? null : hardcodedKeys.find(k => k.split('-')[0].toLowerCase() === langPrefix);
  
  if (matchedKey) {
    message = localizedReview(matchedKey, result, conflicts);
  } else {
    const englishText = getEnglishReview(result, conflicts);
    const originalText = listenBtn.textContent;
    listenBtn.textContent = 'Translating review...';
    listenBtn.disabled = true;
    try {
      const res = await fetch('/api/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: englishText, target_language: language })
      });
      if (!res.ok) throw new Error('Translation failed');
      const resData = await res.json();
      message = resData.translated_text;
    } catch (err) {
      console.error(err);
      message = englishText;
    } finally {
      listenBtn.textContent = originalText;
      listenBtn.disabled = false;
    }
  }
  
  // Show the translated text in the UI
  const transBox = document.querySelector('#translation-box');
  if (transBox) {
    transBox.textContent = `“${message}”`;
    transBox.style.display = 'block';
  }

  // Play speech using Google Translate TTS API for perfect native pronunciation
  try {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    if (window.currentAudio) {
      window.currentAudio.pause();
      window.currentAudio = null;
    }
    const speakLang = isLatn ? 'en' : langPrefix;
    const ttsUrl = `https://translate.google.com/translate_tts?ie=UTF-8&tl=${speakLang}&client=tw-ob&q=${encodeURIComponent(message)}`;
    window.currentAudio = new Audio(ttsUrl);
    const rate = Number(document.querySelector('#voice-rate').value) || 1.0;
    window.currentAudio.playbackRate = rate;
    await window.currentAudio.play();
  } catch (e) {
    console.error("Google TTS failed, falling back to Web Speech API...", e);
    const utterance = new SpeechSynthesisUtterance(message);
    const voices = window.speechSynthesis.getVoices();
    const selected = document.querySelector('#voice-choice').value;
    utterance.voice = voices.find(v => v.voiceURI === selected) || voices.find(v => v.lang.toLowerCase().startsWith(language.toLowerCase())) || null;
    utterance.lang = utterance.voice?.lang || language; utterance.rate = Number(document.querySelector('#voice-rate').value); utterance.pitch = 1;
    window.speechSynthesis.speak(utterance);
  }
}

function populateLanguages() {
  const langSelect = document.querySelector('#voice-language');
  if (!langSelect) return;
  
  const indianLanguages = [
    { code: 'hi-IN', name: 'Hindi (हिन्दी)' },
    { code: 'hi-IN-Latn', name: 'Hindi (English Script / Hinglish)' },
    { code: 'en-IN', name: 'English (India)' },
    { code: 'te-IN', name: 'Telugu (తెలుగు)' },
    { code: 'te-IN-Latn', name: 'Telugu (English Script)' },
    { code: 'ta-IN', name: 'Tamil (தமிழ்)' },
    { code: 'ta-IN-Latn', name: 'Tamil (English Script)' },
    { code: 'kn-IN', name: 'Kannada (ಕನ್ನಡ)' },
    { code: 'kn-IN-Latn', name: 'Kannada (English Script)' },
    { code: 'ml-IN', name: 'Malayalam (മലയാളം)' },
    { code: 'ml-IN-Latn', name: 'Malayalam (English Script)' },
    { code: 'mr-IN', name: 'Marathi (मराठी)' },
    { code: 'bn-IN', name: 'Bengali (বাংলা)' },
    { code: 'gu-IN', name: 'Gujarati (ગુજરાતી)' },
    { code: 'pa-IN', name: 'Punjabi (ਪੰਜਾਬੀ)' },
    { code: 'ur-IN', name: 'Urdu (اردو)' }
  ];
  
  const currentLang = langSelect.value;
  
  langSelect.innerHTML = indianLanguages.map(lang => 
    `<option value="${esc(lang.code)}">${esc(lang.name)}</option>`
  ).join('');
  
  if (indianLanguages.some(l => l.code === currentLang)) {
    langSelect.value = currentLang;
  } else {
    langSelect.value = 'hi-IN';
  }
}


function getEnglishReview(result, conflicts) {
  const blocked = result.decision !== 'RECOMMEND_PROCEED';
  const hasQuantity = conflicts.some(c => /quantity|count|unit/i.test(c.field));
  const hasDamage = conflicts.some(c => /condition|damage|wet|broken/i.test(c.field));
  const issueCount = conflicts.length;
  const copy = {
    title: 'Sakshi review.',
    hold: 'Keep payment on hold.',
    proceed: 'Evidence is consistent, but final payment approval remains with the supervisor.',
    pending: 'Analysis could not be completed. Keep payment pending.',
    quality: 'Evidence quality',
    issues: 'issues were found.',
    none: 'No direct conflict was identified.',
    qty: 'Next action: physically count the delivered material with the foreman.',
    damage: 'Next action: inspect and photograph the damaged material.',
    other: 'Next action: verify the source evidence with the supervisor.'
  };
  const decision = result.decision === 'PENDING_REVIEW' ? copy.pending : blocked ? copy.hold : copy.proceed;
  const conflictLine = issueCount ? `${issueCount} ${copy.issues}` : copy.none;
  const next = hasQuantity ? copy.qty : hasDamage ? copy.damage : copy.other;
  return `${copy.title} ${decision} ${copy.quality}: ${result.evidence_quality?.level || 'LOW'}. ${conflictLine} ${next}`;
}

function updateVoiceOptions() {
  const language = document.querySelector('#voice-language')?.value, select = document.querySelector('#voice-choice');
  if (!language || !select || !('speechSynthesis' in window)) return;
  const voices = window.speechSynthesis.getVoices();
  const matching = voices.filter(v => v.lang.toLowerCase().startsWith(language.toLowerCase())) || [];
  
  const warning = document.querySelector('#voice-warning');
  if (warning) {
    const isLatn = language.toLowerCase().includes('latn');
    if (matching.length === 0 && !isLatn) {
      const selectEl = document.querySelector('#voice-language');
      const langName = selectEl.options[selectEl.selectedIndex].text;
      warning.textContent = `⚠️ Your system doesn't have a ${langName.split(' ')[0]} speech engine installed. Falling back to a default voice, which will skip non-English script.`;
      warning.style.display = 'block';
    } else {
      warning.style.display = 'none';
    }
  }

  const choices = matching.length ? matching : voices.filter(v => v.lang.toLowerCase().startsWith('en-in'));
  const previous = select.value;
  select.innerHTML = choices.length ? choices.map(v => `<option value="${esc(v.voiceURI)}">${esc(v.name)}${v.localService ? ' (device voice)' : ''}</option>`).join('') : '<option value="">Default device voice</option>';
  if ([...select.options].some(option => option.value === previous)) select.value = previous;
}

function localizedReview(language, result, conflicts) {
  const blocked = result.decision !== 'RECOMMEND_PROCEED';
  const hasQuantity = conflicts.some(c => /quantity|count|unit/i.test(c.field));
  const hasDamage = conflicts.some(c => /condition|damage|wet|broken/i.test(c.field));
  const issueCount = conflicts.length;
  const copy = {
    'hi-IN': { title: 'साक्षी समीक्षा।', hold: 'भुगतान रोक कर रखें।', proceed: 'साक्ष्य सही है, लेकिन अंतिम भुगतान सुपरवाइजर की अनुमति के बाद ही होगा।', pending: 'विश्लेषण पूरा नहीं हो सका। भुगतान लंबित रखें।', quality: 'साक्ष्य की गुणवत्ता', issues: 'संदेह या कमियां पाई गई हैं।', none: 'कोई सीधा विरोधाभास नहीं मिला।', qty: 'अगला कदम: सुपरवाइजर के साथ सामग्री की भौतिक गिनती करें।', damage: 'अगला कदम: खराब सामग्री की जांच करें और फोटो लें।', other: 'अगला कदम: साक्ष्यों को सुपरवाइजर से सत्यापित करें।' },
    'te-IN': { title: 'సాక్షి సమీక్ష.', hold: 'చెల్లింపును నిలిపివేయండి.', proceed: 'ఆధారాలు సరిపోతున్నాయి, కానీ తుది చెల్లింపు అనుమతి సూపర్వైజర్‌దే.', pending: 'విశ్లేషణ పూర్తికాలేదు. చెల్లింపును పెండింగ్‌లో ఉంచండి.', quality: 'ఆధారాల నాణ్యత', issues: 'సమస్యలు గుర్తించబడ్డాయి.', none: 'నేరుగా ఏ విభేదం గుర్తించబడలేదు.', qty: 'తదుపరి చర్య: ఫోర్‌మన్‌తో కలిసి సరుకును భౌతికంగా లెక్కించండి.', damage: 'తదుపరి చర్య: దెబ్బతిన్న సరుకును పరిశీలించి ఫోటో తీయండి.', other: 'తదుపరి చర్య: ఆధారాలను సూపర్వైజర్‌తో ధృవీకరించండి.' },
    'ml-IN': { title: 'സാക്ഷി അവലോകനം.', hold: 'പണം നൽകുന്നത് തടഞ്ഞുവയ്ക്കുക.', proceed: 'തെളിവുകൾ യോജിക്കുന്നു, എന്നാൽ അന്തിമ പണമടയ്ക്കൽ അനുമതി സൂപ്പർവൈസറുടേതാണ്.', pending: 'വിശകലനം പൂർത്തിയാക്കാനായില്ല. പണമടയ്ക്കൽ പെൻഡിങ്ങിൽ വയ്ക്കുക.', quality: 'തെളിവിന്റെ നിലവാരം', issues: 'പ്രശ്നങ്ങൾ കണ്ടെത്തി.', none: 'നേരിട്ടുള്ള വൈരുദ്ധ്യം കണ്ടെത്തിയില്ല.', qty: 'അടുത്ത നടപടി: ഫോർമാനൊപ്പം സാധനങ്ങൾ നേരിട്ട് എണ്ണുക.', damage: 'അടുത്ത നടപടി: കേടായ സാധനങ്ങൾ പരിശോധിച്ച് ഫോട്ടോ എടുക്കുക.', other: 'അടുത്ത നടപടി: തെളിവുകൾ സൂപ്പർവൈസറുമായി പരിശോധിക്കുക.' },
    'kn-IN': { title: 'ಸಾಕ್ಷಿ ಪರಿಶೀಲನೆ.', hold: 'ಪಾವತಿಯನ್ನು ತಡೆಹಿಡಿಯಿರಿ.', proceed: 'ಸಾಕ್ಷ್ಯಗಳು ಹೊಂದಿಕೆಯಾಗಿವೆ, ಆದರೆ ಅಂತಿಮ ಪಾವತಿ ಅನುಮತಿ ಮೇಲ್ವಿಚಾರಕರದ್ದಾಗಿದೆ.', pending: 'ವಿಶ್ಲೇಷಣೆ ಪೂರ್ಣವಾಗಲಿಲ್ಲ. ಪಾವತಿಯನ್ನು ಬಾಕಿ ಇರಿಸಿ.', quality: 'ಸಾಕ್ಷ್ಯದ ಗುಣಮಟ್ಟ', issues: 'ಸಮಸ್ಯೆಗಳು ಕಂಡುಬಂದಿವೆ.', none: 'ನೇರವಾದ ವ್ಯತ್ಯಾಸ ಕಂಡುಬಂದಿಲ್ಲ.', qty: 'ಮುಂದಿನ ಕ್ರಮ: ಫೋರ್‌ಮನ್ ಜೊತೆ ಸರಕುಗಳನ್ನು ಭೌತಿಕವಾಗಿ ಎಣಿಸಿ.', damage: 'ಮುಂದಿನ ಕ್ರಮ: ಹಾನಿಯಾದ ಸರಕನ್ನು ಪರಿಶೀಲಿಸಿ ಫೋಟೋ ತೆಗೆದುಕೊಳ್ಳಿ.', other: 'ಮುಂದಿನ ಕ್ರಮ: ಮೇಲ್ವಿಚಾರಕರೊಂದಿಗೆ ಸಾಕ್ಷ್ಯಗಳನ್ನು ಪರಿಶೀಲಿಸಿ.' },
    'en-IN': { title: 'Sakshi review.', hold: 'Keep payment on hold.', proceed: 'Evidence is consistent, but final payment approval remains with the supervisor.', pending: 'Analysis could not be completed. Keep payment pending.', quality: 'Evidence quality', issues: 'issues were found.', none: 'No direct conflict was identified.', qty: 'Next action: physically count the delivered material with the foreman.', damage: 'Next action: inspect and photograph the damaged material.', other: 'Next action: verify the source evidence with the supervisor.' }
  }[language] || {};
  const level = result.evidence_quality?.level || 'LOW';
  const levels = {
    'hi-IN': { 'LOW': '\u0915\u092e', 'MEDIUM': '\u092e\u0927\u094d\u092f\u092e', 'HIGH': '\u0909\u091a\u094d\u091a' },
    'te-IN': { 'LOW': '\u0c24\u0c15\u0c4d\u0c15\u0c41\u0c35', 'MEDIUM': '\u0c2e\u0c27\u0c4d\u0c2f\u0c2e', 'HIGH': '\u0c0e\u0c15\u0c4d\u0c15\u0c41\u0c35' },
    'ml-IN': { 'LOW': '\u0d15\u0d41\u0d31\u0d1e\u0d4d\u0d1e\u0d24\u0d4d', 'MEDIUM': '\u0d2e\u0d3f\u0d24\u0d2e\u0d3e\u0d2f\u0d24\u0d4d', 'HIGH': '\u0d09\u0d2f\u0d7c\u0d28\u0d4d\u0d28\u0d24\u0d4d' },
    'kn-IN': { 'LOW': '\u0c95\u0ca1\u0cbf\u0cae\u0cc6', 'MEDIUM': '\u0cae\u0ca7\u0ccd\u0caf\u0cae', 'HIGH': '\u0cb9\u0cc6\u0c9a\u0ccd\u0c9a\u0cc1' },
    'en-IN': { 'LOW': 'Low', 'MEDIUM': 'Medium', 'HIGH': 'High' }
  }[language] || { 'LOW': 'Low', 'MEDIUM': 'Medium', 'HIGH': 'High' };
  
  const localizedLevel = levels[level] || level;
  const decision = result.decision === 'PENDING_REVIEW' ? copy.pending : blocked ? copy.hold : copy.proceed;
  const conflictLine = issueCount ? `${issueCount} ${copy.issues}` : copy.none;
  const next = hasQuantity ? copy.qty : hasDamage ? copy.damage : copy.other;
  return `${copy.title} ${decision} ${copy.quality}: ${localizedLevel}. ${conflictLine} ${next}`;
}

// --- User Authentication and History Log State ---
function showPage(pageId) {
  document.getElementById('login-page').style.display = pageId === 'login' ? 'flex' : 'none';
  document.getElementById('signup-page').style.display = pageId === 'signup' ? 'flex' : 'none';
  document.getElementById('dashboard-page').style.display = pageId === 'dashboard' ? 'block' : 'none';
}

function initAuth() {
  const token = localStorage.getItem('token');
  const username = localStorage.getItem('username');
  const navUsername = document.getElementById('nav-username');
  
  if (token && username) {
    navUsername.textContent = username;
    showPage('dashboard');
  } else {
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    showPage('login');
  }
}

// Navigation Tab Switching
const comparisonTab = document.getElementById('comparison-tab');
const historyTab = document.getElementById('history-tab');
const navNewBtn = document.getElementById('nav-new-btn');
const navHistoryBtn = document.getElementById('nav-history-btn');

navNewBtn.addEventListener('click', () => {
  comparisonTab.style.display = 'block';
  historyTab.style.display = 'none';
  navNewBtn.classList.add('active');
  navHistoryBtn.classList.remove('active');
});

navHistoryBtn.addEventListener('click', () => {
  comparisonTab.style.display = 'none';
  historyTab.style.display = 'block';
  navHistoryBtn.classList.add('active');
  navNewBtn.classList.remove('active');
  loadHistory();
});

// Logout
document.getElementById('nav-logout-btn').addEventListener('click', () => {
  localStorage.removeItem('token');
  localStorage.removeItem('username');
  initAuth();
  comparisonTab.style.display = 'block';
  historyTab.style.display = 'none';
  navNewBtn.classList.add('active');
  navHistoryBtn.classList.remove('active');
});

// Dedicated Auth Page Navigation
document.getElementById('go-to-signup').addEventListener('click', () => showPage('signup'));
document.getElementById('go-to-login').addEventListener('click', () => showPage('login'));

// Login Form Handler
const loginForm = document.getElementById('login-form');
const loginError = document.getElementById('login-error');
const loginBtn = document.getElementById('login-submit-btn');
loginForm.addEventListener('submit', async event => {
  event.preventDefault();
  loginError.style.display = 'none';
  loginBtn.disabled = true;
  loginBtn.innerHTML = 'Signing in…';
  const email = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value.trim();
  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    const data = await response.json();
    if (!response.ok) throw Error(data.detail || 'Incorrect email or password');
    localStorage.setItem('token', data.access_token);
    localStorage.setItem('username', data.username);
    initAuth();
  } catch (err) {
    loginError.textContent = err.message;
    loginError.style.display = 'block';
  } finally {
    loginBtn.disabled = false;
    loginBtn.innerHTML = 'Sign In <span>→</span>';
  }
});

// Signup Form Handler
const signupForm = document.getElementById('signup-form');
const signupError = document.getElementById('signup-error');
const signupBtn = document.getElementById('signup-submit-btn');
signupForm.addEventListener('submit', async event => {
  event.preventDefault();
  signupError.style.display = 'none';
  signupBtn.disabled = true;
  signupBtn.innerHTML = 'Creating account…';
  const username = document.getElementById('signup-username').value.trim();
  const email = document.getElementById('signup-email').value.trim();
  const password = document.getElementById('signup-password').value.trim();
  try {
    const response = await fetch('/api/auth/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, email, password })
    });
    const data = await response.json();
    if (!response.ok) throw Error(data.detail || 'Registration failed');
    
    // Auto-login after signup
    const loginResponse = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    const loginData = await loginResponse.json();
    if (!loginResponse.ok) throw Error(loginData.detail || 'Auto-login failed');
    localStorage.setItem('token', loginData.access_token);
    localStorage.setItem('username', loginData.username);
    initAuth();
  } catch (err) {
    signupError.textContent = err.message;
    signupError.style.display = 'block';
  } finally {
    signupBtn.disabled = false;
    signupBtn.innerHTML = 'Create Account <span>→</span>';
  }
});

// Load History Records
async function loadHistory() {
  const historyList = document.getElementById('history-list');
  const token = localStorage.getItem('token');
  if (!token) return;
  
  historyList.innerHTML = '<div class="loading">Fetching audit trail...</div>';
  try {
    const response = await fetch('/api/history/list', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await response.json();
    if (!response.ok) throw Error(data.detail || 'Could not fetch history');
    
    if (data.length === 0) {
      historyList.innerHTML = '<div class="card" style="grid-column: 1/-1; text-align: center; padding: 40px;"><p>No previous reconciliations found. Run a check to populate history.</p></div>';
      return;
    }
    
    historyList.innerHTML = data.map(record => {
      const decision = record.result_data?.decision || 'PENDING_REVIEW';
      const score = record.result_data?.evidence_quality?.score ?? 0;
      const level = record.result_data?.evidence_quality?.level || 'LOW';
      const createdStr = new Date(record.created_at).toLocaleString();
      const hasValidImg = record.image_url && (record.image_url.startsWith('/') || record.image_url.startsWith('http') || record.image_url.startsWith('data:'));
      const imageTag = hasValidImg ? `<img src="${esc(record.image_url)}" alt="Challan" onclick="window.open('${esc(record.image_url)}', '_blank')">` : '<div style="background:#f4f4f0; height:140px; display:flex; align-items:center; justify-content:center; color:#777; font-size:12px; border:1px dashed #ccc; margin-bottom:12px;">No image recorded</div>';
      const audioTag = record.audio_url ? `<audio controls src="${esc(record.audio_url)}"></audio>` : '<small style="display:block; margin-top:10px; color:#888;">No voice note uploaded</small>';
      
      return `
        <div class="history-card" id="history-card-${esc(record.id)}">
          <div class="history-card-top">
            <span class="badge ${esc(decision)}">${esc(decision).replaceAll('_', ' ')}</span>
            <small style="color:#666; font-family:monospace; display:block; margin-bottom:8px;">ID: #${esc(record.id)} · ${esc(createdStr)}</small>
            ${imageTag}
            <p class="eyebrow" style="margin-top:10px;">Foreman Transcript</p>
            <blockquote style="font-size:14px; margin: 5px 0 10px; border-left: 2px solid var(--line); padding-left:8px;">“${esc(record.transcript)}”</blockquote>
            ${audioTag}
            <p class="eyebrow" style="margin-top:15px;">Safety Audit Score</p>
            <strong>${esc(level)} <small>(${esc(score)}/100)</small></strong>
          </div>
          <button class="delete-btn" type="button" onclick="deleteHistoryRecord('${esc(record.id)}')">Delete Comparison</button>
        </div>
      `;
    }).join('');
  } catch (err) {
    historyList.innerHTML = `<div class="card error" style="grid-column:1/-1;"><h3>Failed to load history</h3><p>${esc(err.message)}</p></div>`;
  }
}

// Delete History Record
async function deleteHistoryRecord(id) {
  if (!confirm('Are you sure you want to delete this reconciliation record?')) return;
  const token = localStorage.getItem('token');
  if (!token) return;
  
  try {
    const response = await fetch(`/api/history/delete/${id}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!response.ok) {
      const data = await response.json();
      throw Error(data.detail || 'Failed to delete record');
    }
    const card = document.getElementById(`history-card-${id}`);
    if (card) {
      card.style.opacity = '0';
      setTimeout(() => card.remove(), 300);
    }
  } catch (err) {
    alert(`Error deleting record: ${err.message}`);
  }
}

// Initialize on page load
initAuth();
