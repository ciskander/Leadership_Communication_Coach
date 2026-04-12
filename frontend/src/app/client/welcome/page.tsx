'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { dismissWelcome } from '@/lib/onboarding';
import { STRINGS } from '@/config/strings';

const S = STRINGS.onboarding;

// Icon paths matching the sidebar nav (24×24 stroke viewport)
const stepIcons: string[][] = [
  // layers — Baseline Analysis
  [
    'M12 2L3 7L12 12L21 7L12 2Z',
    'M3 12L12 17L21 12',
    'M3 17L12 22L21 17',
  ],
  // sparkles — Analyze Meeting
  [
    'M9 3L10.5 7.5L15 9L10.5 10.5L9 15L7.5 10.5L3 9L7.5 7.5L9 3Z',
    'M19 13L19.75 15.25L22 16L19.75 16.75L19 19L18.25 16.75L16 16L18.25 15.25L19 13Z',
  ],
  // beaker — Experiment
  [
    'M9 3H15',
    'M9 3V9L4 18H20L15 9V3',
    'M7.5 14H16.5',
  ],
  // trendingUp — Progress
  [
    'M3 17L9 11L13 15L21 7',
    'M15 7H21V13',
  ],
];

const steps = [
  { num: 1, title: S.journeyStep1Title, desc: S.journeyStep1Desc, tag: 'One time',      icon: stepIcons[0] },
  { num: 2, title: S.journeyStep2Title, desc: S.journeyStep2Desc, tag: 'Each meeting',   icon: stepIcons[1] },
  { num: 3, title: S.journeyStep3Title, desc: S.journeyStep3Desc, tag: 'One at a time',  icon: stepIcons[2] },
  { num: 4, title: S.journeyStep4Title, desc: S.journeyStep4Desc, tag: 'Over time',      icon: stepIcons[3] },
];

const expectations = [S.expectItem1, S.expectItem2, S.expectItem3];

// ─── Disclosure / Accordion ─────────────────────────────────────────────────

function DisclosureSection({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-white border border-cv-warm-300 rounded overflow-hidden">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-3 px-5 py-4 text-left hover:bg-cv-warm-100 transition-colors"
      >
        <span className="text-sm font-medium text-cv-stone-900">{title}</span>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`w-4 h-4 text-cv-stone-400 shrink-0 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
          aria-hidden="true"
        >
          <path d="M6 9L12 15L18 9" />
        </svg>
      </button>
      {open && (
        <div className="border-t border-cv-warm-300 px-5 py-4">
          {children}
        </div>
      )}
    </div>
  );
}

// ─── Illustrations ──────────────────────────────────────────────────────────

function IllustrationExecSummary() {
  return (
    <div className="max-w-xs mt-3 rounded border border-cv-warm-300 overflow-hidden" aria-hidden="true">
      <div className="bg-cv-navy-600 px-3 py-2 flex items-center gap-2">
        <div className="w-3 h-3 rounded-sm bg-cv-blue-50/30" />
        <div className="h-2 w-14 rounded-full bg-cv-blue-50/50" />
      </div>
      <div className="px-3 py-2.5 space-y-1.5">
        <div className="h-2 w-full rounded-full bg-cv-stone-200" />
        <div className="h-2 w-5/6 rounded-full bg-cv-stone-200" />
        <div className="h-2 w-4/6 rounded-full bg-cv-stone-200" />
      </div>
    </div>
  );
}

function IllustrationCoachingThemes() {
  return (
    <div className="max-w-xs mt-3 flex gap-2" aria-hidden="true">
      {/* Strengths card */}
      <div className="flex-1 rounded border border-cv-teal-700 overflow-hidden">
        <div className="bg-cv-teal-700 px-2.5 py-1.5">
          <div className="h-2 w-16 rounded-full bg-cv-teal-50/50" />
        </div>
        <div className="px-2.5 py-2 space-y-1.5">
          <div className="h-1.5 w-full rounded-full bg-cv-warm-200" />
          <div className="h-1.5 w-4/5 rounded-full bg-cv-warm-200" />
        </div>
      </div>
      {/* Themes card */}
      <div className="flex-1 rounded border border-cv-rose-700 overflow-hidden">
        <div className="bg-cv-rose-700 px-2.5 py-1.5">
          <div className="h-2 w-12 rounded-full bg-cv-rose-50/50" />
        </div>
        <div className="px-2.5 py-2 space-y-1.5">
          <div className="h-1.5 w-full rounded-full bg-cv-warm-200" />
          <div className="h-1.5 w-3/5 rounded-full bg-cv-warm-200" />
        </div>
      </div>
    </div>
  );
}

function IllustrationPatterns() {
  return (
    <div className="max-w-xs mt-3 flex gap-6" aria-hidden="true">
      <div>
        <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-stone-400 mb-2">Task</p>
        <div className="grid grid-cols-3 gap-1.5">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="w-5 h-5 rounded-full bg-cv-teal-600/15 border border-cv-teal-600/30" />
          ))}
        </div>
      </div>
      <div>
        <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-stone-400 mb-2">Relational</p>
        <div className="grid grid-cols-3 gap-1.5">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="w-5 h-5 rounded-full bg-cv-rose-600/15 border border-cv-rose-600/30" />
          ))}
        </div>
      </div>
    </div>
  );
}

function IllustrationScoring() {
  const bars = [
    { pct: '82%', w: 'w-[82%]', color: 'bg-cv-teal-500' },
    { pct: '61%', w: 'w-[61%]', color: 'bg-cv-amber-400' },
    { pct: '38%', w: 'w-[38%]', color: 'bg-cv-red-400' },
  ];
  return (
    <div className="max-w-xs mt-3 space-y-2" aria-hidden="true">
      {bars.map((bar) => (
        <div key={bar.pct} className="flex items-center gap-2">
          <div className="flex-1 bg-cv-warm-200 rounded-full h-1.5 overflow-hidden">
            <div className={`h-1.5 rounded-full ${bar.color} ${bar.w}`} />
          </div>
          <span className="text-xs tabular-nums text-cv-stone-500 w-9 text-right">{bar.pct}</span>
        </div>
      ))}
    </div>
  );
}

function IllustrationTrendlines() {
  return (
    <div className="max-w-xs mt-3" aria-hidden="true">
      <div className="flex items-baseline gap-1.5 mb-1">
        <span className="text-lg font-bold tabular-nums text-cv-stone-800">74%</span>
        <span className="text-xs text-cv-teal-600 font-semibold">&uarr; +6</span>
      </div>
      <svg viewBox="0 0 200 40" className="w-full h-8" fill="none">
        {/* baseline reference */}
        <line x1="0" y1="28" x2="200" y2="28" stroke="#A8A29E" strokeWidth="1" strokeDasharray="4 4" />
        {/* trend line */}
        <polyline
          points="0,32 40,30 80,26 120,22 160,16 200,12"
          stroke="#0F6E56"
          strokeWidth="1.5"
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="200" cy="12" r="3" fill="#0F6E56" stroke="white" strokeWidth="1.5" />
      </svg>
    </div>
  );
}

function IllustrationPatternCoaching() {
  return (
    <div className="max-w-xs mt-3 rounded border border-cv-warm-300 overflow-hidden" aria-hidden="true">
      <div className="px-3 py-2.5 space-y-2">
        {/* Quote block */}
        <div className="border-l-[2px] border-cv-navy-600 pl-3 py-1.5 bg-cv-blue-50 rounded-r">
          <div className="h-1.5 w-20 rounded-full bg-cv-stone-300 mb-1" />
          <div className="h-1.5 w-full rounded-full bg-cv-stone-200" />
        </div>
        {/* Rewrite block */}
        <div className="border-l-[2px] border-cv-teal-700 pl-3 py-1.5 bg-cv-teal-50 rounded-r">
          <div className="h-1.5 w-24 rounded-full bg-cv-teal-600/20 mb-1" />
          <div className="h-1.5 w-full rounded-full bg-cv-teal-600/15" />
        </div>
      </div>
    </div>
  );
}

function IllustrationEvidenceQuotes() {
  return (
    <div className="max-w-xs mt-3 space-y-2" aria-hidden="true">
      {/* Target speaker */}
      <div className="border-l-[2px] border-cv-navy-600 pl-3 py-1.5 bg-cv-blue-50 rounded-r">
        <div className="h-1.5 w-12 rounded-full bg-cv-stone-300 mb-1" />
        <div className="h-1.5 w-full rounded-full bg-cv-stone-200" />
        <div className="h-1.5 w-3/4 rounded-full bg-cv-stone-200 mt-1" />
      </div>
      {/* Other speaker */}
      <div className="border-l-[2px] border-cv-stone-300 pl-3 py-1.5 bg-cv-warm-100 rounded-r">
        <div className="h-1.5 w-14 rounded-full bg-cv-stone-300 mb-1" />
        <div className="h-1.5 w-5/6 rounded-full bg-cv-stone-200" />
      </div>
    </div>
  );
}

function IllustrationSuggestedRewrites() {
  return (
    <div className="max-w-xs mt-3" aria-hidden="true">
      <div className="border-l-[2px] border-cv-teal-700 pl-3 py-2 bg-cv-teal-50 rounded-r">
        <p className="text-2xs text-cv-stone-400 italic mb-1">&ldquo;Next time, try something like&hellip;&rdquo;</p>
        <div className="h-1.5 w-full rounded-full bg-cv-teal-600/15" />
        <div className="h-1.5 w-4/5 rounded-full bg-cv-teal-600/15 mt-1" />
      </div>
    </div>
  );
}

function IllustrationExperimentWorkflow() {
  const stages = ['Propose', 'Accept', 'Detect', 'Track', 'Graduate'];
  return (
    <div className="max-w-xs mt-3 flex items-center gap-0" aria-hidden="true">
      {stages.map((label, i) => (
        <div key={label} className="flex items-center">
          <div className="flex flex-col items-center">
            <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[7px] font-bold ${
              i === 0 ? 'bg-cv-teal-600 text-white' : 'bg-cv-warm-200 text-cv-stone-500'
            }`}>
              {i + 1}
            </div>
            <span className="text-[9px] text-cv-stone-400 mt-1 whitespace-nowrap">{label}</span>
          </div>
          {i < stages.length - 1 && (
            <div className="w-5 h-px bg-cv-stone-300 mb-4" />
          )}
        </div>
      ))}
    </div>
  );
}

function IllustrationProgressTracking() {
  return (
    <div className="max-w-xs mt-3" aria-hidden="true">
      <svg viewBox="0 0 200 50" className="w-full h-10" fill="none">
        <line x1="0" y1="45" x2="200" y2="45" stroke="#E7E5E4" strokeWidth="0.5" />
        <line x1="0" y1="30" x2="200" y2="30" stroke="#E7E5E4" strokeWidth="0.5" />
        <line x1="0" y1="15" x2="200" y2="15" stroke="#E7E5E4" strokeWidth="0.5" />
        {/* Line 1 - teal */}
        <polyline points="0,35 50,30 100,24 150,18 200,14" stroke="#0F6E56" strokeWidth="1.5" strokeLinecap="round" />
        {/* Line 2 - amber */}
        <polyline points="0,38 50,36 100,32 150,34 200,30" stroke="#D97706" strokeWidth="1.5" strokeLinecap="round" />
        {/* Line 3 - stone */}
        <polyline points="0,42 50,40 100,38 150,36 200,35" stroke="#A8A29E" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
      <div className="flex gap-3 mt-1">
        <div className="flex items-center gap-1"><div className="w-2.5 h-2.5 rounded-full bg-[#0F6E56]" /><span className="text-[9px] text-cv-stone-400">Pattern A</span></div>
        <div className="flex items-center gap-1"><div className="w-2.5 h-2.5 rounded-full bg-[#D97706]" /><span className="text-[9px] text-cv-stone-400">Pattern B</span></div>
        <div className="flex items-center gap-1"><div className="w-2.5 h-2.5 rounded-full bg-[#A8A29E]" /><span className="text-[9px] text-cv-stone-400">Pattern C</span></div>
      </div>
    </div>
  );
}

function IllustrationBaselinePack() {
  return (
    <div className="max-w-xs mt-3 relative h-20" aria-hidden="true">
      {/* Three stacked meeting cards */}
      {[2, 1, 0].map((i) => (
        <div
          key={i}
          className="absolute rounded border border-cv-warm-300 bg-white"
          style={{ left: i * 6, top: i * 4, width: 80, height: 44 }}
        >
          <div className="bg-cv-stone-100 px-2 py-1 border-b border-cv-warm-300 rounded-t">
            <div className="h-1.5 w-10 rounded-full bg-cv-stone-300" />
          </div>
          <div className="px-2 py-1.5">
            <div className="h-1 w-12 rounded-full bg-cv-warm-200" />
          </div>
        </div>
      ))}
      {/* Arrow */}
      <svg viewBox="0 0 30 20" className="absolute w-6 h-5" style={{ left: 100, top: 14 }} fill="none">
        <path d="M2 10H26M26 10L20 4M26 10L20 16" stroke="#A8A29E" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {/* Aggregate card */}
      <div
        className="absolute rounded border-2 border-cv-teal-700 bg-white"
        style={{ left: 132, top: 4, width: 90, height: 52 }}
      >
        <div className="bg-cv-teal-700 px-2 py-1.5 rounded-t-[3px]">
          <div className="h-2 w-14 rounded-full bg-cv-teal-50/50" />
        </div>
        <div className="px-2 py-1.5 space-y-1">
          <div className="h-1 w-16 rounded-full bg-cv-warm-200" />
          <div className="h-1 w-12 rounded-full bg-cv-warm-200" />
          <div className="h-1 w-14 rounded-full bg-cv-warm-200" />
        </div>
      </div>
    </div>
  );
}

// ─── Preview sections data ──────────────────────────────────────────────────

const previewSections: { title: string; desc: string; Illustration: React.FC }[] = [
  { title: S.previewExecSummaryTitle,         desc: S.previewExecSummaryDesc,         Illustration: IllustrationExecSummary },
  { title: S.previewCoachingThemesTitle,      desc: S.previewCoachingThemesDesc,      Illustration: IllustrationCoachingThemes },
  { title: S.previewPatternsTitle,            desc: S.previewPatternsDesc,            Illustration: IllustrationPatterns },
  { title: S.previewScoringTitle,             desc: S.previewScoringDesc,             Illustration: IllustrationScoring },
  { title: S.previewTrendlinesTitle,          desc: S.previewTrendlinesDesc,          Illustration: IllustrationTrendlines },
  { title: S.previewPatternCoachingTitle,     desc: S.previewPatternCoachingDesc,     Illustration: IllustrationPatternCoaching },
  { title: S.previewEvidenceQuotesTitle,      desc: S.previewEvidenceQuotesDesc,      Illustration: IllustrationEvidenceQuotes },
  { title: S.previewSuggestedRewritesTitle,   desc: S.previewSuggestedRewritesDesc,   Illustration: IllustrationSuggestedRewrites },
  { title: S.previewExperimentWorkflowTitle,  desc: S.previewExperimentWorkflowDesc,  Illustration: IllustrationExperimentWorkflow },
  { title: S.previewProgressTrackingTitle,    desc: S.previewProgressTrackingDesc,    Illustration: IllustrationProgressTracking },
  { title: S.previewBaselinePackTitle,        desc: S.previewBaselinePackDesc,        Illustration: IllustrationBaselinePack },
];

// ─── Page ───────────────────────────────────────────────────────────────────

export default function WelcomePage() {
  const router = useRouter();

  function handleGetStarted() {
    dismissWelcome();
    router.push('/client');
  }

  function handleSkip() {
    dismissWelcome();
    router.push('/client');
  }

  return (
    <div className="max-w-2xl mx-auto py-6 px-2">

      {/* Skip */}
      <div className="flex justify-end mb-2">
        <button
          onClick={handleSkip}
          className="text-2xs font-medium tracking-widest uppercase text-cv-stone-400 hover:text-cv-stone-600 transition-colors"
        >
          {S.skip} ↗
        </button>
      </div>

      {/* Hero */}
      <section className="py-10 border-b border-cv-warm-300">
        <p className="text-2xs font-medium tracking-widest uppercase text-cv-teal-400 mb-4">
          {S.welcomeHeading}
        </p>
        <h1 className="font-serif text-3xl text-cv-stone-900 mb-4 leading-tight">
          Coaching rooted in<br />
          what you <em className="italic text-cv-teal-600">actually</em> said.
        </h1>
        <p className="text-base text-cv-stone-600 font-light leading-relaxed max-w-md">
          {S.welcomeIntro}
        </p>
      </section>

      {/* Steps */}
      <section className="py-10 border-b border-cv-warm-300">
        <p className="text-2xs font-medium tracking-widest uppercase text-cv-stone-400 mb-7">
          {S.journeyHeading}
        </p>
        <div className="flex flex-col divide-y divide-black/5">
          {steps.map((step) => (
            <div key={step.num} className="flex gap-6 py-5 items-start">
              <div className="w-7 h-7 rounded-full border border-cv-teal-200 bg-cv-teal-600/5 flex items-center justify-center flex-shrink-0 mt-0.5">
                <span className="text-xs font-medium text-cv-teal-600">{step.num}</span>
              </div>
              <div className="flex-1">
                <p className="text-sm font-medium text-cv-stone-900 mb-1 flex items-center gap-1.5">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" className="w-3.5 h-3.5 shrink-0 text-cv-teal-600" aria-hidden="true">
                    {step.icon.map((d, i) => <path key={i} d={d} />)}
                  </svg>
                  {step.title}
                </p>
                <p className="text-sm text-cv-stone-400 font-light leading-relaxed">{step.desc}</p>
                <span className="inline-block mt-2 text-2xs font-medium tracking-wide uppercase text-cv-teal-400 bg-cv-teal-400/10 border border-cv-teal-700 px-2 py-0.5 rounded">
                  {step.tag}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* What to expect */}
      <section className="py-10 border-b border-cv-warm-300">
        <p className="text-2xs font-medium tracking-widest uppercase text-cv-stone-400 mb-5">
          {S.expectHeading}
        </p>
        <div className="flex flex-col gap-3.5">
          {expectations.map((text, i) => (
            <div key={i} className="flex items-start gap-3.5">
              <div className="w-1 h-1 rounded-full bg-cv-teal-400 flex-shrink-0 mt-2" />
              <p className="text-sm text-cv-stone-600 font-light leading-relaxed">{text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* What you'll see */}
      <section className="py-10 border-b border-cv-warm-300">
        <p className="text-2xs font-medium tracking-widest uppercase text-cv-stone-400 mb-2">
          {S.whatYoullSeeHeading}
        </p>
        <p className="text-sm text-cv-stone-500 font-light leading-relaxed mb-5">
          {S.whatYoullSeeIntro}
        </p>
        <div className="flex flex-col gap-2">
          {previewSections.map(({ title, desc, Illustration }) => (
            <DisclosureSection key={title} title={title}>
              <p className="text-sm text-cv-stone-600 font-light leading-relaxed">{desc}</p>
              <Illustration />
            </DisclosureSection>
          ))}
        </div>
      </section>

      {/* CTA */}
      <div className="flex items-center gap-5 pt-10">
        <button
          onClick={handleGetStarted}
          className="bg-cv-teal-600 text-cv-teal-50 px-9 py-3.5 rounded text-sm font-medium tracking-wide hover:bg-cv-teal-800 transition-colors"
        >
          {S.getStarted}
        </button>
        <span className="text-xs text-cv-stone-400 font-light italic">
          Takes about 5 minutes to complete your baseline.
        </span>
      </div>

    </div>
  );
}
