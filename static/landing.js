/* ═══════════════════════════════════════════════════════════════
   Vanilla JS Implementation of TextPressure Animation
   Adapted from the React component provided.
   ═══════════════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {
    const text = 'MEDBOT PRO';
    const minFontSize = 36;
    
    const container = document.getElementById('text-pressure-container');
    if (!container) return;

    // Create the Title Element
    const title = document.createElement('h1');
    title.className = 'text-pressure-title';
    container.appendChild(title);

    // Create character spans
    const chars = text.split('');
    const spans = [];
    
    chars.forEach(char => {
        const span = document.createElement('span');
        span.textContent = char;
        span.setAttribute('data-char', char);
        title.appendChild(span);
        spans.push(span);
    });

    const mouse = { x: 0, y: 0 };
    const cursor = { x: 0, y: 0 };
    
    // Setup initial cursor position to center of screen
    const setInitialCursor = () => {
        const rect = container.getBoundingClientRect();
        mouse.x = rect.left + rect.width / 2;
        mouse.y = rect.top + rect.height / 2;
        cursor.x = mouse.x;
        cursor.y = mouse.y;
    };
    setInitialCursor();

    // Event Listeners for Mouse/Touch
    const handleMouseMove = (e) => {
        cursor.x = e.clientX;
        cursor.y = e.clientY;
    };
    
    const handleTouchMove = (e) => {
        const t = e.touches[0];
        cursor.x = t.clientX;
        cursor.y = t.clientY;
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('touchmove', handleTouchMove, { passive: true });

    // Handle Sizing
    let currentScaleY = 1;
    const setSize = () => {
        const containerRect = container.getBoundingClientRect();
        
        // Calculate font size to fit container
        let newFontSize = containerRect.width / (chars.length / 1.5);
        newFontSize = Math.max(newFontSize, minFontSize);
        
        title.style.fontSize = `${newFontSize}px`;
        
        // Let layout recalculate, then adjust scaleY
        requestAnimationFrame(() => {
            const textRect = title.getBoundingClientRect();
            // Since we don't strictly have a fixed height container for scale in this design,
            // we will keep scaleY at 1 unless we want it to stretch. For hero texts, stretching is optional.
            // Let's implement a gentle vertical scale if needed, or stick to 1.
            title.style.transform = `scale(1, 1)`;
            title.style.lineHeight = '1';
        });
    };

    // Debounce resize
    let resizeTimeout;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(setSize, 100);
    });
    
    // Initial size calculation (give fonts time to load)
    setTimeout(setSize, 100);
    document.fonts.ready.then(setSize);

    // Math Utils
    const dist = (a, b) => {
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        return Math.sqrt(dx * dx + dy * dy);
    };

    const getAttr = (distance, maxDist, minVal, maxVal) => {
        const val = maxVal - Math.abs((maxVal * distance) / maxDist);
        return Math.max(minVal, val + minVal);
    };

    // Animation Loop
    let rafId;
    const animate = () => {
        // Smooth cursor follow
        mouse.x += (cursor.x - mouse.x) / 15;
        mouse.y += (cursor.y - mouse.y) / 15;

        const titleRect = title.getBoundingClientRect();
        const maxDist = titleRect.width / 2;

        spans.forEach(span => {
            const rect = span.getBoundingClientRect();
            const charCenter = {
                x: rect.x + rect.width / 2,
                y: rect.y + rect.height / 2
            };

            const d = dist(mouse, charCenter);

            // Calculate font-variation-settings based on distance
            const wdth = Math.floor(getAttr(d, maxDist, 5, 200));
            const wght = Math.floor(getAttr(d, maxDist, 100, 900));
            const italVal = getAttr(d, maxDist, 0, 1).toFixed(2);
            // Optionally adjust alpha if desired:
            // const alphaVal = getAttr(d, maxDist, 0.2, 1).toFixed(2);

            const newFontVariationSettings = `'wght' ${wght}, 'wdth' ${wdth}, 'ital' ${italVal}`;

            if (span.style.fontVariationSettings !== newFontVariationSettings) {
                span.style.fontVariationSettings = newFontVariationSettings;
            }
        });

        rafId = requestAnimationFrame(animate);
    };

    animate();
});
