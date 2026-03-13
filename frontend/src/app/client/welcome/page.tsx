'use client';

import { useRouter } from 'next/navigation';
import { dismissWelcome } from '@/lib/onboarding';
import { STRINGS } from '@/config/strings';

const S = STRINGS.onboarding;

const steps = [
  { num: 1, title: S.journeyStep1Title, desc: S.journeyStep1Desc, tag: 'One time' },
  { num: 2, title: S.journeyStep2Title, desc: S.journeyStep2Desc, tag: 'Each meeting' },
  { num: 3, title: S.journeyStep3Title, desc: S.journeyStep3Desc, tag: 'One at a time' },
  { num: 4, title: S.journeyStep4Title, desc: S.journeyStep4Desc, tag: 'Over time' },
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
                <p className="text-sm font-medium text-cv-stone-900 mb-1">{step.title}</p>
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
