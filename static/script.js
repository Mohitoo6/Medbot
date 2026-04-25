/* ═══════════════════════════════════════════════════════════════
   MedBot v4 — Premium Medical Chat UI
   Splash screen, typewriter effects, scroll management, and chat engine
   ═══════════════════════════════════════════════════════════════ */
(() => {
    'use strict';

    const state = { sessionId: null, isLoading: false, sidebarOpen: false, hasScrolledUp: false };
    const $ = id => document.getElementById(id);
    const D = {
        input: $('chat-input'),
        sendBtn: $('send-btn'),
        msgList: $('messages-list'),
        scroll: $('messages-scroll'),
        typing: $('typing-indicator'),
        welcome: $('welcome'),
        counter: $('counter'),
        statusDot: document.querySelector('.status-dot'),
        statusLabel: $('status-label'),
        statChunks: $('stat-chunks'),
        statModel: $('stat-model'),
        modelSelect: $('model-select'),
        inputWrap: $('input-wrap'),
        sidebar: $('sidebar'),
        hamburger: $('hamburger'),
        backdrop: $('mobile-backdrop'),
        btnNew: $('btn-new-chat'),
        btnClear: $('btn-clear-chat'),
        splash: $('splash-screen'),
        greeting: $('greeting-text'),
        scrollFab: $('scroll-fab')
    };

    /* ══════════════════════════════════════════
       1. UI EFFECTS & INITIALIZATION
    ══════════════════════════════════════════ */
    
    function initSplash() {
        // Only show splash on initial load if no session exists
        if (D.splash) {
            setTimeout(() => {
                D.splash.classList.add('hide');
                // Start welcome animations after splash hides
                setTimeout(typewriterGreeting, 400);
            }, 2500);
        } else {
            typewriterGreeting();
        }
    }

    function typewriterGreeting() {
        if (!D.greeting) return;
        const text = "Hello, Clinician.";
        D.greeting.textContent = "";
        let i = 0;
        
        function typeWriter() {
            if (i < text.length) {
                D.greeting.textContent += text.charAt(i);
                i++;
                setTimeout(typeWriter, 50 + Math.random() * 50); // random delay for realism
            }
        }
        
        // Add a slight delay before typing starts
        setTimeout(typeWriter, 200);
    }

    /* ══════════════════════════════════════════
       2. MARKDOWN RENDERER
    ══════════════════════════════════════════ */
    function md(raw) {
        if (!raw) return '';
        let h = raw.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

        h = h.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, l, c) => `<pre><code class="lang-${l}">${c.trim()}</code></pre>`);
        h = h.replace(/`([^`\n]+)`/g, '<code>$1</code>');

        h = h.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
        h = h.replace(/^### (.+)$/gm, '<h3>$1</h3>');
        h = h.replace(/^## (.+)$/gm, '<h2>$1</h2>');
        h = h.replace(/^# (.+)$/gm, '<h1>$1</h1>');

        h = h.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
        h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        h = h.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');

        h = h.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');
        h = h.replace(/^---+$/gm, '<hr>');

        h = h.replace(/^[\s]*[-*•] (.+)$/gm, '<li>$1</li>');
        h = h.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');

        h = h.replace(/^\d+\. (.+)$/gm, '<oli>$1</oli>');
        h = h.replace(/((?:<oli>.*<\/oli>\n?)+)/g, m =>
            '<ol>' + m.replace(/<oli>/g, '<li>').replace(/<\/oli>/g, '</li>') + '</ol>');

        const lines = h.split('\n');
        let inT = false;
        const out = lines.map(line => {
            const t = line.trim();
            if (t.startsWith('|') && t.endsWith('|')) {
                const cells = t.slice(1, -1).split('|').map(c => c.trim());
                if (cells.every(c => /^[-:]+$/.test(c))) { inT = true; return ''; }
                const tag = !inT ? 'th' : 'td';
                if (!inT) inT = true;
                return '<tr>' + cells.map(c => `<${tag}>${c}</${tag}>`).join('') + '</tr>';
            }
            if (inT) { inT = false; return '</tbody></table>' + line; }
            return line;
        });
        h = out.join('\n');
        h = h.replace(/(<tr>.*<\/tr>(\n|$))+/g, m => `<table><tbody>${m}</tbody></table>`);

        const blocks = h.split(/\n{2,}/);
        h = blocks.map(b => {
            const t = b.trim();
            if (!t) return '';
            if (/^<(h[1-6]|ul|ol|pre|table|blockquote|hr)/.test(t)) return t;
            return `<p>${t.replace(/\n/g, '<br>')}</p>`;
        }).join('\n');

        return h;
    }

    /* ══════════════════════════════════════════
       3. CHAT ENGINE & SCROLLING
    ══════════════════════════════════════════ */
    function esc(t) { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }
    function ts() { return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
    
    function scrollEnd(force = false) { 
        if (!D.scroll) return;
        // Don't auto-scroll if user has manually scrolled up, unless forced
        if (state.hasScrolledUp && !force) return;
        requestAnimationFrame(() => { 
            D.scroll.scrollTop = D.scroll.scrollHeight; 
            state.hasScrolledUp = false;
        }); 
    }

    // Monitor scrolling to show/hide FAB and pause auto-scroll
    if (D.scroll) {
        D.scroll.addEventListener('scroll', () => {
            const isAtBottom = D.scroll.scrollHeight - D.scroll.scrollTop <= D.scroll.clientHeight + 50;
            state.hasScrolledUp = !isAtBottom;
            
            if (D.scrollFab) {
                if (state.hasScrolledUp) {
                    D.scrollFab.classList.add('visible');
                } else {
                    D.scrollFab.classList.remove('visible');
                }
            }
        }, { passive: true });
    }

    if (D.scrollFab) {
        D.scrollFab.addEventListener('click', () => {
            state.hasScrolledUp = false;
            scrollEnd(true);
        });
    }

    function addMsg(content, role, sources = []) {
        if (D.welcome) D.welcome.style.display = 'none';

        const wrap = document.createElement('div');
        wrap.className = `msg msg--${role}`;

        const avHTML = role === 'user'
            ? `<div class="msg-avatar">You</div>`
            : `<div class="msg-avatar">💊</div>`;

        let bodyHTML;
        if (role === 'user') {
            bodyHTML = `<div class="msg-bubble"><div class="msg-body">${esc(content)}</div><div class="msg-time">${ts()}</div></div>`;
        } else {
            const srcHTML = sources.length
                ? `<div class="msg-sources">${sources.map(s =>
                    `<span class="src-tag">📄 ${s.book} · ${s.section}</span>`
                ).join('')}</div>`
                : '<div class="msg-sources" style="display:none"></div>';
            bodyHTML = `<div class="msg-bubble"><div class="msg-body">${md(content)}</div>${srcHTML}<div class="msg-time">${ts()}</div></div>`;
        }

        wrap.innerHTML = avHTML + bodyHTML;
        if (D.msgList) D.msgList.appendChild(wrap);
        scrollEnd(true); // Force scroll on new message
        return wrap;
    }

    function setLoading(on) {
        state.isLoading = on;
        if (D.sendBtn) {
            D.sendBtn.disabled = on || !D.input.value.trim();
            if (on) D.sendBtn.classList.add('sending');
            else D.sendBtn.classList.remove('sending');
        }
        if (D.input) D.input.disabled = on;
        if (D.typing) D.typing.style.display = on ? 'flex' : 'none';
        if (on) scrollEnd(true);
    }

    async function send(text) {
        const msg = text.trim();
        if (!msg || state.isLoading) return;

        addMsg(msg, 'user');
        if (D.input) { D.input.value = ''; autoH(); }
        updateCounter();
        setLoading(true);
        state.hasScrolledUp = false; // Reset scroll state when sending

        try {
            const selectedModel = D.modelSelect ? D.modelSelect.value : undefined;
            const r = await fetch(window.location.origin + '/api/chat_stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: msg, session_id: state.sessionId, model: selectedModel }),
            });

            if (!r.ok) {
                if (r.status === 404) throw new Error("API endpoint not found. Server configuration issue.");
                if (r.status === 500) throw new Error("Internal server error. Model API might be rate-limited or the backend crashed.");
                throw new Error(`HTTP ${r.status}`);
            }

            // Hide typing indicator immediately when stream connects
            if (D.typing) D.typing.style.display = 'none';

            const reader = r.body.getReader();
            const decoder = new TextDecoder("utf-8");

            const botMsgEl = addMsg('', 'bot');
            const msgBodyEl = botMsgEl.querySelector('.msg-body');
            const msgSourcesEl = botMsgEl.querySelector('.msg-sources');
            let fullAnswer = '';

            // Add streaming cursor
            msgBodyEl.classList.add('streaming-cursor');

            let buffer = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');

                // Keep the last partial line in the buffer
                buffer = lines.pop();

                for (const line of lines) {
                    if (!line.trim()) continue;
                    try {
                        const obj = JSON.parse(line);
                        if (obj.type === "metadata" && obj.sources && obj.sources.length > 0) {
                            msgSourcesEl.style.display = 'flex';
                            msgSourcesEl.innerHTML = obj.sources.map(s => `<span class="src-tag">📄 ${s.book} · ${s.section}</span>`).join('');
                        } else if (obj.type === "chunk") {
                            fullAnswer += obj.content;
                            msgBodyEl.innerHTML = md(fullAnswer);
                            scrollEnd();
                        } else if (obj.type === "session") {
                            state.sessionId = obj.session_id;
                        } else if (obj.type === "error") {
                            addMsg(`⚠️ **Error:** ${obj.content}`, 'bot');
                        }
                    } catch (e) {
                        console.warn("Could not parse NDJSON line:", line);
                    }
                }
            }
            msgBodyEl.classList.remove('streaming-cursor');
            
            // Format any remaining buffer
            if (buffer.trim()) {
                 try {
                     const obj = JSON.parse(buffer);
                     if (obj.type === "chunk") {
                         fullAnswer += obj.content;
                         msgBodyEl.innerHTML = md(fullAnswer);
                     }
                 } catch(e){}
            }

        } catch (err) {
            console.error("Chat flow error:", err);
            let errMsg = err.message;
            if (errMsg.toLowerCase().includes("failed to fetch")) {
                errMsg = "Could not connect to the local MedBot backend server. Please verify the `start.sh` script is running in your terminal.";
            }
            addMsg(`⚠️ **Connection Error:** ${errMsg}\n\nPlease try again or restart the server using \`./start.sh\`.`, 'bot');
        } finally {
            setLoading(false);
            if (window.innerWidth > 768 && D.input) D.input.focus();
        }
    }
    window.medbotSend = send;

    /* ══════════════════════════════════════════
       4. UI & MOBILE EVENTS
    ══════════════════════════════════════════ */
    function autoH() {
        if (!D.input) return;
        D.input.style.height = 'auto';
        D.input.style.height = Math.min(D.input.scrollHeight, 120) + 'px';
    }

    function updateCounter() {
        if (!D.input || !D.counter) return;
        const n = D.input.value.length;
        D.counter.textContent = `${n} / 2000`;
        D.counter.classList.toggle('warn', n > 1800);
        if (D.sendBtn) D.sendBtn.disabled = !D.input.value.trim() || state.isLoading;
    }

    if (D.input) {
        D.input.addEventListener('input', () => { updateCounter(); autoH(); });
        D.input.addEventListener('focus', () => D.inputWrap?.classList.add('focused'));
        D.input.addEventListener('blur', () => D.inputWrap?.classList.remove('focused'));
        D.input.addEventListener('keydown', e => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                // Check button instead of state.isLoading to respect button disabled state
                if (!D.sendBtn.disabled && D.input.value.trim()) send(D.input.value);
            }
        });
    }

    D.sendBtn?.addEventListener('click', () => { if (D.input.value.trim() && !D.sendBtn.disabled) send(D.input.value); });

    D.modelSelect?.addEventListener('change', (e) => {
        const short = e.target.value.split('/').pop().replace(':free', '');
        if (D.statModel) D.statModel.textContent = short;
    });

    document.querySelectorAll('.sug-card').forEach(btn => {
        btn.addEventListener('click', () => { const q = btn.dataset.query; if (q) send(q); });
    });

    function toggleSidebar(close) {
        state.sidebarOpen = close ? false : !state.sidebarOpen;
        
        if (window.innerWidth > 768) {
            // Desktop: toggle collapsed class
            D.sidebar?.classList.toggle('collapsed', !state.sidebarOpen);
            localStorage.setItem('sidebarCollapsed', !state.sidebarOpen);
        } else {
            // Mobile: toggle open class
            D.sidebar?.classList.toggle('open', state.sidebarOpen);
            D.backdrop?.classList.toggle('active', state.sidebarOpen);
        }
    }

    D.hamburger?.addEventListener('click', () => toggleSidebar());
    D.backdrop?.addEventListener('click', () => toggleSidebar(true));

    function resetChat() {
        state.sessionId = null;
        if (D.msgList) D.msgList.innerHTML = '';
        if (D.welcome) D.welcome.style.display = '';
        if (D.input) { D.input.value = ''; updateCounter(); autoH(); }
        typewriterGreeting(); // Retrigger the greeting typing effect
        if (state.sidebarOpen) toggleSidebar(true);
    }

    D.btnNew?.addEventListener('click', resetChat);
    D.btnClear?.addEventListener('click', async () => {
        if (state.sessionId) {
            try { await fetch('/api/clear', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: state.sessionId }) }); } catch { }
        }
        resetChat();
    });

    /* ══════════════════════════════════════════
       5. HEALTH CHECK
    ══════════════════════════════════════════ */
    async function checkHealth() {
        try {
            const [hr, sr] = await Promise.all([fetch('/api/health'), fetch('/api/stats')]);
            const h = await hr.json(), s = await sr.json();

            if (h.database_ready) {
                D.statusDot?.classList.add('online');
                if (D.statusLabel) D.statusLabel.textContent = 'Online · Ready';
            }
            if (s.total_chunks && D.statChunks) D.statChunks.textContent = s.total_chunks.toLocaleString();
            if (s.llm_model && !D.modelSelect) {
                const short = s.llm_model.split('/').pop().replace(':free', '');
                if (D.statModel) D.statModel.textContent = short;
            } else if (D.modelSelect) {
                const short = D.modelSelect.value.split('/').pop().replace(':free', '');
                if (D.statModel) D.statModel.textContent = short;
            }
        } catch {
            if (D.statusLabel) D.statusLabel.textContent = 'Offline';
            D.statusDot?.classList.remove('online');
        }
    }

    checkHealth();
    setInterval(checkHealth, 30000);



    /* ══════════════════════════════════════════
       7. INIT
    ══════════════════════════════════════════ */
    function init() {
        initSplash();

        // Initialize desktop sidebar state
        if (window.innerWidth > 768) {
            const isCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
            state.sidebarOpen = !isCollapsed;
            if (isCollapsed) D.sidebar?.classList.add('collapsed');
        }

        if (window.innerWidth > 768 && D.input) {
            D.input.focus();
        }
        console.log('%c💊 MedBot v4 — Premium UI', 'color:#00E5A0;font-weight:700;font-size:14px');
    }

    document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', init) : init();
})();
