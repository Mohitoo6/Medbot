import React from 'react';
import { createRoot } from 'react-dom/client';
import SoftAurora from './SoftAurora.jsx';
import LogoLoop from './LogoLoop.jsx';

// ── Soft Aurora Background ──
const auroraContainer = document.getElementById('liquid-bg');
if (auroraContainer) {
  const root = createRoot(auroraContainer);
  root.render(
    <SoftAurora
      speed={0.6}
      scale={1.5}
      brightness={1.0}
      color1="#f7f7f7"
      color2="#e100ff"
      noiseFrequency={2.5}
      noiseAmplitude={1.0}
      bandHeight={0.5}
      bandSpread={1.0}
      octaveDecay={0.1}
      layerOffset={0}
      colorSpeed={1.0}
      enableMouseInteraction={true}
      mouseInfluence={0.25}
    />
  );
}

// ── Looping Suggestions ──
const prompts = [
    { title: "Apixaban Monitoring", query: "Mechanism of action and monitoring for Apixaban in atrial fibrillation.", icon: "🫀" },
    { title: "Sildenafil Interactions", query: "Common drug interactions and contraindications for Sildenafil.", icon: "💊" },
    { title: "Metformin Side Effects", query: "Management of Metformin-associated gastrointestinal side effects.", icon: "🔬" },
    { title: "Lisinopril vs Losartan", query: "Comparison of Lisinopril vs. Losartan for hypertension management.", icon: "📈" },
    { title: "Vancomycin Dosing", query: "Pharmacokinetics and dosing of Vancomycin in renal impairment.", icon: "📋" },
    { title: "Atorvastatin Counseling", query: "Adverse effects and counseling points for Atorvastatin therapy.", icon: "🩺" },
    { title: "Empagliflozin Pearls", query: "Mechanism and clinical pearls for Empagliflozin in heart failure.", icon: "🩹" },
    { title: "Sertraline Interactions", query: "Interactions between Sertraline and common OTC medications.", icon: "🧠" },
    { title: "Gabapentin in Elderly", query: "Dosage adjustments for Gabapentin in elderly patients.", icon: "👴" }
];

const SuggestionItem = ({ prompt }) => {
    const handleClick = () => {
        if (window.medbotSend) {
            window.medbotSend(prompt.query);
        }
    };

    return (
        <div 
            className="sug-card" 
            onClick={handleClick}
            style={{ 
                width: '320px', 
                margin: '0', 
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'row',
                alignItems: 'center',
                gap: '12px',
                textAlign: 'left',
                flexShrink: 0,
                fontSize: '1rem',
                height: '90px', // slightly taller
                padding: '0 20px',
                overflow: 'hidden'
            }}
        >
            <div className="sug-icon" style={{ fontSize: '1.4rem', flexShrink: 0 }}>{prompt.icon}</div>
            <div className="sug-text" style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
                <strong style={{ display: 'block', fontSize: '0.9rem', marginBottom: '2px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{prompt.title}</strong>
                <span style={{ fontSize: '0.75rem', opacity: 0.7, display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {prompt.query}
                </span>
            </div>
            <div className="sug-arrow" style={{ flexShrink: 0, opacity: 0.5 }}>→</div>
        </div>
    );
};

const suggestionsContainer = document.getElementById('suggestions');
if (suggestionsContainer) {
    const root = createRoot(suggestionsContainer);
    
    const logoItems = prompts.map(p => ({
        node: <SuggestionItem prompt={p} />
    }));

    root.render(
        <div style={{ width: '100vw', marginLeft: 'calc(-50vw + 50%)', padding: '30px 0' }}>
            <LogoLoop
                logos={logoItems}
                speed={35}
                direction="left"
                logoHeight={90} 
                gap={30}
                fadeOut={true}
                pauseOnHover={true}
            />
        </div>
    );
}
