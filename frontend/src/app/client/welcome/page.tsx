'use client';

import { useRouter } from 'next/navigation';
import { dismissWelcome } from '@/lib/onboarding';
import { STRINGS } from '@/config/strings';

const S = STRINGS.onboarding;

// Icon paths matching the sidebar nav (24×24 stroke viewport)
const stepIcons: string[][] = [
  // layers — Baseline Pack
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
      <section className="py-10 border-b border-cv-warm-border">
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
      <section className="py-10 border-b border-cv-warm-border">
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
                <span className="inline-block mt-2 text-2xs font-medium tracking-wide uppercase text-cv-teal-400 bg-cv-teal-400/10 px-2 py-0.5 rounded">
                  {step.tag}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* What to expect */}
      <section className="py-10 border-b border-cv-warm-border">
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

      {/* CTA */}
      <div className="flex items-center gap-5 pt-10">
        <button
          onClick={handleGetStarted}
          className="bg-cv-teal-600 text-cv-teal-50 px-9 py-3.5 rounded-lg text-sm font-medium tracking-wide hover:bg-cv-teal-800 transition-colors"
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
