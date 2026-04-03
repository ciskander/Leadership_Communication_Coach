/**
 * Centralised UI strings for the Leadership Communication Coach frontend.
 *
 * All user-visible text should live here so it can be customised without
 * touching component code. Dynamic strings that depend on runtime values
 * are expressed as functions.
 */

// ─── Shared / reusable ─────────────────────────────────────────────────────────

export const STRINGS = {
  // ── App-wide ────────────────────────────────────────────────────────────────
  app: {
    title: 'ClearVoice',
    description: 'AI-powered leadership communication coaching',
    loginHeading: 'ClearVoice',
    loginSubheading: 'AI-powered communication coaching rooted in your actual meetings.',
    continueWithGoogle: 'Continue with Google',
    signOut: 'Sign out',
    redirectingToSignIn: 'Redirecting to sign in…',
  },

  // ── Brand / logo ────────────────────────────────────────────────────────────
  brand: {
    logoAlt: 'ClearVoice',
    logoAriaLabel: 'ClearVoice Leadership Communication Coaching',
    wordmarkLeft: 'Clear',
    wordmarkRight: 'Voice',
    subtitle: 'LEADERSHIP COMMUNICATION COACHING',
    sidebarHint: 'ClearVoice helps you become a more effective communicator, one meeting at a time.',
  },

  // ── Navigation ──────────────────────────────────────────────────────────────
  nav: {
    home: 'Home',
    baselinePack: 'Baseline Analysis',
    analyzeMeeting: 'Analyze Meeting',
    myExperiment: 'My Experiment',
    progress: 'Progress',
    myCoachees: 'My Coachees',
    runAnalysis: 'Run Analysis',
    users: 'Users',
    dashboard: '← Dashboard',
  },

  // ── Common labels ───────────────────────────────────────────────────────────
  common: {
    whatToDo: 'What to do',
    successLooksLike: 'Success looks like',
    howYoullKnowItWorked: "How you'll know it worked",
    forExampleYouSaid: 'For example, in this meeting you said',
    referringToExampleAbove: 'Referring to the example above',
    nextTimeTry: 'Next time, try something like',
    whatYouDidWell: 'What you did well',
    whereYouCanImprove: 'Where you can improve',
    observation: 'Observation',
    cancel: 'Cancel',
    delete: 'Delete',
    deleting: 'Deleting…',
    saving: 'Saving…',
    uploading: 'Uploading…',
    loading: 'Loading…',
    retry: 'Retry',
    decideLater: 'Decide later',
    acceptExperiment: 'Accept experiment',
    accepting: 'Accepting…',
    meetingAnalysis: 'Meeting Analysis',
    baselinePackAnalysis: 'Baseline Analysis',
    untitled: 'Untitled',
    meeting: 'Meeting',
    noExplanationAvailable: 'No explanation available.',
  },

  // ── Role labels (shared across multiple pages) ──────────────────────────────
  roles: {
    chair: 'Chair',
    presenter: 'Presenter',
    participant: 'Participant',
    manager_1to1: 'Manager (1:1)',
    report_1to1: 'Report (1:1)',
  } as Record<string, string>,

  // ── Role options (for dropdowns) ────────────────────────────────────────────
  roleOptions: [
    { value: 'chair', label: 'Chair / Facilitator' },
    { value: 'presenter', label: 'Presenter' },
    { value: 'participant', label: 'Participant' },
    { value: 'manager_1to1', label: '1:1 Manager' },
    { value: 'report_1to1', label: '1:1 Report' },
  ],

  // ── Pattern labels ──────────────────────────────────────────────────────────
  patternLabels: {
    purposeful_framing: 'Purposeful Framing',
    focus_management: 'Focus Management',
    disagreement_navigation: 'Disagreement Navigation',
    trust_and_credibility: 'Trust & Credibility',
    resolution_and_alignment: 'Resolution & Alignment',
    assignment_clarity: 'Assignment Clarity',
    question_quality: 'Question Quality',
    communication_clarity: 'Communication Clarity',
    feedback_quality: 'Feedback Quality',
  } as Record<string, string>,

  // ── Pattern explanations (used in progress page popovers) ───────────────────
  patternExplanations: {
    purposeful_framing:
      'Whether you frame topics with both a named subject and a desired outcome — when opening the meeting and at each transition. Scored on two elements: topic identification and stated outcome.',
    focus_management:
      'Whether you keep discussion aligned with stated objectives when conversation drifts. Scored on how explicitly you name the departure and redirect or sanction it.',
    disagreement_navigation:
      'How you handle moments of disagreement or pushback. Scored on whether you engage with the substance, acknowledge the opposing view, maintain solution focus, and drive toward resolution.',
    trust_and_credibility:
      'Whether your behavior during high-stakes moments builds or erodes trust with the room. Scored on ownership, engagement with expertise, consistency between words and actions, and how you use authority.',
    resolution_and_alignment:
      'Whether you close discussions with a clear statement of what was decided and an explicit check that the group agrees. Scored on two elements: named resolution and alignment confirmation.',
    assignment_clarity:
      'Whether assignments include the elements needed for success — owner, deadline, and deliverable for simple tasks, plus context and confirmation for complex ones. Scoring scales with assignment complexity.',
    question_quality:
      'Whether your questions serve a clear purpose — advancing a decision, surfacing assumptions, broadening perspective, or testing constraints — rather than being aimless or leading.',
    communication_clarity:
      'Whether your substantive contributions are clear and structured — leading with your main point, responding to the actual question, and keeping length proportionate to complexity.',
    feedback_quality:
      'Whether you deliver feedback using a structured approach: grounding it in a specific situation and behavior, naming the impact, offering a recommendation, and checking in with the recipient (SBI-RC).',
  } as Record<string, string>,

  // ── Pattern icons (legacy — components now use inline SVG; keep for any unconverted usage) ─────
  patternIcons: {
    purposeful_framing: '🎯',
    focus_management: '🧭',
    disagreement_navigation: '🤝',
    trust_and_credibility: '🛡️',
    resolution_and_alignment: '✅',
    assignment_clarity: '📋',
    question_quality: '❓',
    communication_clarity: '💬',
    feedback_quality: '📣',
  } as Record<string, string>,

  // ── Cluster metadata ──────────────────────────────────────────────────────
  clusterLabels: {
    meeting_structure: 'Meeting Structure & Direction',
    participation_dynamics: 'Participation & Interpersonal Dynamics',
    decisions_accountability: 'Decisions & Accountability',
    communication_quality: 'Communication Quality',
  } as Record<string, string>,

  clusterOrder: [
    'meeting_structure',
    'participation_dynamics',
    'decisions_accountability',
    'communication_quality',
  ] as string[],

  // ── Highlight badges (shown on pattern cards in cluster view) ────────────
  highlightBadges: {
    strength: 'Strength',
    focus: 'Focus area',
  },

  // ── Trend sparkline labels ──────────────────────────────────────────────────
  trendSparkline: {
    stable: 'Stable',
  },

  // ── Evaluable status labels ─────────────────────────────────────────────────
  evaluableStatus: {
    insufficient_signal: 'Insufficient signal',
    not_evaluable: 'Not evaluable',
  } as Record<string, string>,

  // ── Experiment status labels ────────────────────────────────────────────────
  experimentStatus: {
    proposed: 'Proposed',
    active: 'Active',
    completed: 'Completed',
    parked: 'Parked',
    abandoned: 'Abandoned',
  } as Record<string, string>,

  // ── Attempt status labels ───────────────────────────────────────────────────
  attemptLabels: {
    yes: 'Attempted',
    partial: 'Partial attempt',
    no: 'Not attempted',
  } as Record<string, string>,

  // ── Human confirmation labels ───────────────────────────────────────────────
  humanConfirmation: {
    confirmed_attempt: '↩ You confirmed',
    confirmed_no_attempt: '↩ You said no',
    tooltip: 'Your confirmation',
  },

  // ── Baseline badge labels ───────────────────────────────────────────────────
  baselineStatus: {
    none: 'Not started',
    intake: 'Uploading',
    building: 'Building',
    baseline_ready: 'Ready',
    completed: 'Ready',
    error: 'Error',
  } as Record<string, string>,

  // ── Coaching card ───────────────────────────────────────────────────────────
  coachingCard: {
    strengthsHeading: 'What you do well',
    focusHeading: 'Area to focus on',
    experimentHeading: 'Your experiment',
    coachingThemesHeading: 'Key coaching themes',
  },

  // ── Transcript upload ───────────────────────────────────────────────────────
  transcriptUpload: {
    clickToUpload: 'Click to upload transcript (.vtt, .srt, .txt, .docx, .pdf)',
    clickToSelect: 'Click to select transcript (.vtt, .srt, .txt, .docx, .pdf)',
    fileUploaded: '✓ File uploaded',
    fileUploadedSuccess: 'File uploaded successfully',
    uploadTranscript: 'Upload transcript',
    meetingTitle: 'Meeting title',
    meetingTitlePlaceholder: 'e.g. Q1 Planning Session',
    meetingType: 'Meeting type',
    selectType: 'Select type…',
    otherTypeBelow: 'Other (type below)',
    enterMeetingType: 'Enter meeting type',
    meetingDate: 'Meeting date',
    meetingDateAutodetect: '(will be auto-detected if found in transcript)',
  },

  // ── Run status poller ───────────────────────────────────────────────────────
  runStatusPoller: {
    analysing: 'Analyzing your meeting',
    stillWorking: 'Still working…',
    usuallyTakes: 'This usually takes 30–60 seconds',
    timeoutTitle: 'Taking longer than expected',
    timeoutDesc: 'The analysis is still running in the background.',
    checkAgain: 'Check again',
    errorTitle: 'Analysis failed',
    errorFallback: 'Something went wrong. Please try again.',
    qualityCheckFailed: "Quality check didn't pass",
    qualityCheckDesc:
      "The AI output didn't meet our quality requirements. This sometimes happens with shorter or unclear transcripts. Try re-running with a cleaner transcript.",
    tryAnotherTranscript: 'Try another transcript',
    analysisComplete: 'Analysis complete',
    analysisFeedback: "Here's your personalised coaching feedback",
    summaryHeading: 'Summary',
    coachingThemesHeading: 'Key Coaching Themes',
    primaryThemeLabel: 'Primary',
    secondaryThemeLabel: 'Secondary',
    experimentSectionHeading: 'Experiment',
    patternSnapshot: 'Detailed Feedback',
    otherPatterns: 'Coaching output for other patterns',
    showDetails: 'Show details',
    hideDetails: 'Hide details',
    // Experiment tracking
    experimentAccepted: 'Experiment accepted — good luck!',
    viewOnDashboard: 'View on dashboard →',
    experimentReady: 'Your experiment is ready',
    fromTranscript: 'From the transcript',
    whatYouSaid: 'What you said',
    whatYouDidWell: 'What you did well',
    whatWorkedMissing: 'What worked and what was missing',
    coachsNote: "Coach's note",
    currentExperiment: 'Current Experiment',
    inThisMeeting: 'In this meeting',
    yourExperiment: 'Your experiment',
    viewOnMyExperiment: 'View on My Experiment →',
    // Detection
    nicelyDone: 'Nicely done!',
    partialAttemptDetected: 'Partial attempt detected',
    userConfirmedAttempt: 'User confirmed attempt',
    noAttemptDetected: 'No attempt detected',
    missedDetectionPrompt:
      "The model didn\u2019t detect your experiment being tried in this meeting \u2014 but it\u2019s possible we missed something. Did you attempt the experiment?",
    yesITriedIt: 'Yes, I tried it',
    notThisTime: 'Not this time',
    confirmedYes:
      "Thanks for letting us know! We\u2019ve recorded your attempt \u2014 the model doesn\u2019t always catch everything.",
    confirmedNo:
      'Got it \u2014 no worries. Just a gentle reminder to try again next time.',
    clearAttempts: (count: number | string) =>
      `The model detected ${count ?? 'multiple'} clear attempt${(typeof count === 'number' && count !== 1) || count === 'multiple' ? 's' : ''} at your experiment in this meeting. Keep it up.`,
    partialAttemptDesc: (count: number | null) =>
      `You made a partial attempt at your experiment${count ? ` — ${count} instance${count !== 1 ? 's' : ''} noted` : ''}. You're on the right track.`,
    // Graduation / parking recommendations
    graduationRecommendationTitle: 'Ready to graduate',
    parkRecommendationTitle: 'Consider parking this experiment',
  },

  // ── Experiment tracker ──────────────────────────────────────────────────────
  experimentTracker: {
    analyzeToStart: 'Analyze your next meeting to start tracking this experiment.',
    analyzeToContinue: 'Analyze your next meeting to continue tracking this experiment.',
    analyzeMeeting: 'Analyze Meeting',
    noAttemptsYet: (meetings: number) =>
      `No attempts detected yet across ${meetings} meeting${meetings !== 1 ? 's' : ''}. Keep going — it takes a few tries to build the habit.`,
    attemptsDetected: (attempts: number, meetings: number) =>
      `${attempts} attempt${attempts !== 1 ? 's' : ''} detected across ${meetings} meeting${meetings !== 1 ? 's' : ''} analyzed.`,
    fullAttempts: 'Full attempts',
    partial: 'Partial',
    meetings: 'Meetings',
    attemptHistory: 'Attempt history',
    parkConfirmTitle: 'Park this experiment for now?',
    parkConfirmDesc:
      'Your experiment will be saved so you can resume it later if you choose. We\'ll keep track of any progress recorded so far.',
    yesParkIt: 'Yes, park it',
    keepGoing: 'Keep going',
    markComplete: 'Mark complete ✓',
    parkForNow: 'Park for now',
  },

  // ── Client dashboard (home) ─────────────────────────────────────────────────
  clientDashboard: {
    greetingMorning: 'Good morning',
    greetingAfternoon: 'Good afternoon',
    greetingEvening: 'Good evening',
    subtitle: 'Your communication growth dashboard.',
    yourJourney: 'Your Journey',
    journeyBaseline: 'Baseline',
    journeyFirstAnalysis: 'First Analysis',
    journeyExperiment: 'Experiment',
    journeyGrowth: 'Growth',
    startBaseline: 'Start by building your baseline from three past meetings.',
    getStarted: 'Get started →',
    buildingBaseline: 'Building your baseline… check back in a few minutes.',
    experimentOptionsWaiting: 'You have experiment options waiting — pick one to get started.',
    chooseExperiment: 'Choose experiment →',
    baselineReadyAnalyze: 'Baseline ready! Analyze a meeting to receive your first experiment suggestion.',
    analyzeMeetingArrow: 'Analyze Meeting →',
    baselinePackTitle: 'Baseline Analysis',
    baselinePackCta: 'Analyze three past meetings to unlock personalised coaching patterns.',
    baselinePackDone: '✓ Your communication patterns have been mapped.',
    analysisInProgress: 'Analysis in progress…',
    createBaseline: 'Create baseline',
    activeExperimentTitle: 'Active Experiment',
    trackProgress: 'Track progress →',
    experimentOptionsChoose: 'Choose one →',
    experimentOptionsWaitingShort: 'You have experiment options waiting.',
    completeAnalysisForExperiment: 'Complete an analysis to receive your first personalised experiment.',
    suggestedExperiments: 'Suggested Experiments',
    suggestions: (n: number) => `${n} suggestion${n !== 1 ? 's' : ''}`,
    analyzeMeetingBtn: 'Analyze Meeting',
    createBaselineBtn: 'Create Baseline',
    recentAnalyses: 'Recent Analyses',
    deleteSelected: (n: number) => `Delete selected (${n})`,
    done: 'Done',
    edit: 'Edit',
    editModeHelp: 'Select meetings to delete. Baseline Analysis cannot be deleted here.',
    baselineCannotDeleteTooltip: 'Baseline Analysis cannot be deleted here',
    completeCurrentFirst: 'Complete your current experiment first',
    accept: 'Accept',
    deleteModalTitle: (count: number) => `Delete ${count === 1 ? 'this meeting' : `${count} meetings`}?`,
    deleteModalDesc: (count: number) =>
      `This will permanently delete the ${count === 1 ? 'meeting' : 'meetings'} and ${count === 1 ? 'its' : 'their'} analysis results. This cannot be undone.`,
    attemptCount: (attempts: number, meetings?: number) => {
      let s = `${attempts} attempt${attempts !== 1 ? 's' : ''}`;
      if (meetings != null && meetings > 0) s += ` across ${meetings} meeting${meetings !== 1 ? 's' : ''}`;
      return s;
    },
    deletionsFailed: (count: number) => `${count} deletion${count > 1 ? 's' : ''} failed. Please try again.`,
  },

  // ── Analyze page ────────────────────────────────────────────────────────────
  analyzePage: {
    heading: 'Analyze a Meeting',
    subtitle: 'Upload a transcript to receive personalised coaching feedback.',
    step1: 'Upload transcript',
    step2: 'Configure analysis',
    whichSpeaker: 'Which speaker are you?',
    whoAreWeAnalysing: 'Who are we analyzing?',
    speakerLabel: 'Speaker label',
    speakerLabelPlaceholder: 'e.g. SPEAKER_00',
    fullName: 'Their full name',
    fullNamePlaceholder: 'e.g. Sarah Johnson',
    roleInMeeting: 'Their role in this meeting',
    selectRole: 'Select role…',
    submitBtn: 'Analyze Meeting →',
    startingAnalysis: 'Starting analysis…',
    analysisInProgress: 'Analyzing your meeting…',
    // Errors
    failedToEnqueue: 'Failed to enqueue',
    analysisFailedToStart: 'Analysis failed to start.',
    timedOutWaiting: 'Timed out waiting for analysis to start.',
    analysisStillRunning: 'Analysis is taking longer than expected. Please check back shortly — your results will appear on the dashboard when ready.',
    checkNow: 'Check now',
    stillProcessing: 'Still processing — check back in a minute.',
    backToDashboard: 'Back to dashboard',
    failedToPollStatus: 'Failed to poll status.',
  },

  // ── Baseline new page ───────────────────────────────────────────────────────
  baselineNew: {
    heading: 'Create Baseline Analysis',
    subtitle: 'Select three past meeting transcripts to build your communication baseline.',
    yourFullName: 'Your full name',
    nameHint: 'Used to identify you across all three transcripts.',
    namePlaceholder: 'e.g. Sarah Johnson',
    meetingsConfigured: (n: number) => `${n} of 3 meetings configured`,
    loadingTranscripts: 'Loading your transcripts…',
    meetingN: (n: number) => `Meeting ${n}`,
    existing: 'Existing',
    uploadNew: 'Upload new',
    noTranscripts: 'No transcripts yet.',
    uploadOne: 'Upload one',
    yourSpeakerLabel: 'Your speaker label in this transcript',
    noDateWarning: '⚠ No date set — required for correct ordering in your progress chart.',
    yourRole: 'Your role in this meeting',
    selectPlaceholder: 'Select…',
    buildingBaseline: 'Building baseline…',
    buildBaselineBtn: 'Build Baseline Analysis →',
  },

  // ── Baseline detail page ────────────────────────────────────────────────────
  baselineDetail: {
    heading: 'Baseline Analysis',
    notFound: 'Baseline analysis not found.',
    buildingTitle: 'Building your baseline…',
    buildingDesc: 'This may take up to 15 minutes. This page will update automatically.',
    timeoutTitle: 'Build is taking longer than expected',
    errorTitle: 'Baseline build failed',
    timeoutDesc: 'The analysis is still running in the background. Check back in a few minutes, or try creating a new baseline analysis.',
    errorDesc: 'Something went wrong during analysis. Please try creating a new baseline analysis.',
    tryAgain: 'Try again',
    completeTitle: 'Baseline analysis complete',
    completeSubtitle: 'Your communication patterns have been mapped across three meetings',
    yourBaseline: 'Your communication baseline',
    otherPatterns: 'Coaching output for other patterns',
    meetingsInBaseline: 'Meetings in this baseline',
    coachingOutput: 'Coaching output',
    patternScores: 'Pattern scores',
    expand: '▼ Expand',
    collapse: '▲ Collapse',
    noAnalysisData: 'Analysis data is not available for this meeting.',
    notAnalysedYet: 'This meeting has not been analyzed yet.',
    experimentAccepted: 'Experiment accepted',
    trackExperiment: 'Track progress on My Experiment →',
    experimentReady: 'Your experiment is ready',
    loadingExperiment: 'Loading your experiment…',
    aggregateCoachingNote: 'For personalized coaching based on specific meeting excerpts, take a look at the individual meeting sections below.',
  },

  // ── Experiment page ─────────────────────────────────────────────────────────
  experimentPage: {
    heading: 'My Experiment',
    subtitle: 'Track your progress on your current communication experiment.',
    completeBanner: 'Experiment complete — well done!',
    completeSubtext: 'Ready for your next challenge? Pick one below.',
    parkedBanner: 'Experiment parked.',
    parkedSubtext: 'You can resume it anytime. Pick your next focus below.',
    findingExperiment: 'Finding your next experiment…',
    generatingOptions: 'Generating your experiment options…',
    parkCapMessage: (count: number) =>
      `You have ${count} parked experiment${count !== 1 ? 's' : ''} (the maximum).`,
    parkCapHint: 'Resume one to continue, or discard one to free up space for new suggestions.',
    recommendedNext: 'Recommended next experiment',
    suggestedExperiment: 'Suggested Experiment',
    seeMoreOptions: 'See more options',
    chooseNext: 'Choose your next experiment',
    backToRecommendation: 'Back to recommendation',
    topPick: 'Top pick',
    rankLabel: (rank: number) => rank === 1 ? 'Top pick' : `Option ${rank}`,
    previouslyParked: 'Previously parked',
    newSuggestionsArriving: 'New suggestions arriving shortly…',
    orResumeParked: 'Or resume a parked experiment',
    resumeParked: 'Resume a parked experiment',
    noActiveExperiment: 'No active experiment',
    noActiveExperimentDesc: 'Complete a baseline analysis or single-meeting analysis to receive your first personalised experiment.',
    // Parked experiment card
    parked: 'Parked',
    resumeExperiment: 'Resume experiment',
    resuming: 'Resuming…',
    discard: 'Discard',
    discardConfirm: 'Permanently discard this experiment? This cannot be undone.',
  },

  // ── Progress page ───────────────────────────────────────────────────────────
  progressPage: {
    heading: 'Your Progress',
    subtitle: 'Pattern trends over time and your experiment history.',
    loading: 'Loading your progress…',
    errorFallback: 'Failed to load progress data.',
    patternTrends: 'Pattern Trends',
    experimentPatterns: 'Experiment Patterns',
    top5Patterns: 'Top 5 Patterns',
    allPatterns: 'All Patterns',
    noRunData: 'No run data yet. Analyze a meeting to see your trends.',
    meetingsUntilTrends: (n: number) =>
      `${n} more meeting${n !== 1 ? 's' : ''} until trends appear`,
    experimentBadge: 'Experiment',
    baseline: 'Baseline',
    score: 'Score',
    pastExperiments: 'Past Experiments',
    noPastExperiments: 'No completed, parked, or abandoned experiments yet.',
    pattern: 'Pattern',
    dateRange: 'Date range',
    attempts: 'Attempts',
    id: 'ID',
    duringExperiment: (label: string) => `${label} during experiment`,
    oneMeeting: '(1 meeting)',
    attemptsAcross: (attempts: number, meetings: number) =>
      `${attempts}${meetings > 0 ? ` across ${meetings} meeting${meetings !== 1 ? 's' : ''}` : ''}`,
  },

  // ── Run results page ────────────────────────────────────────────────────────
  runResults: {
    deleteThisMeeting: 'Delete this meeting',
    deleteModalTitle: 'Delete this meeting?',
    deleteModalDesc: 'This will permanently delete the meeting and its analysis results. This cannot be undone.',
    deletionFailed: 'Deletion failed. Please try again.',
  },

  // ── Coach dashboard ─────────────────────────────────────────────────────────
  coachDashboard: {
    heading: 'My Coachees',
    emptySubtitle: 'Add your first coachee to get started.',
    subtitle: (n: number) => `${n} coachee${n !== 1 ? 's' : ''} in your programme.`,
    addCoachee: 'Add Coachee',
    noCoacheesTitle: 'No coachees yet',
    noCoacheesDesc: 'Search for existing users or invite new ones.',
    viewProfile: 'View profile',
    // Modal
    addCoacheeModalTitle: 'Add Coachee',
    findExistingUser: 'Find Existing User',
    inviteNewUser: 'Invite New User',
    searchPlaceholder: 'Search by name or email…',
    noUsersFound: 'No users found matching that search.',
    searchFailed: 'Search failed. Please try again.',
    failedToAssign: 'Failed to assign coachee.',
    typeAtLeast2: 'Type at least 2 characters to search.',
    inviteDesc: "Generate a single-use invite link to send to a new coachee. They'll be linked to your account when they sign up.",
    generateInviteLink: 'Generate Invite Link',
    generating: 'Generating…',
    copied: '✓ Copied!',
    copyLink: 'Copy Link',
    new: 'New',
    add: 'Add',
    unnamed: 'Unnamed',
  },

  // ── Coach analyze page ──────────────────────────────────────────────────────
  coachAnalyze: {
    heading: 'Run Analysis',
    subtitle: 'Upload a transcript and run coaching analysis for one of your coachees.',
    step1: 'Step 1 — Select Coachee',
    noCoachees: 'No coachees yet.',
    inviteFirst: 'Invite one first.',
    step2: 'Step 2 — Upload Transcript',
    step3: 'Step 3 — Configure Analysis',
    targetSpeaker: 'Target speaker',
    speakersFullName: "Speaker's full name",
    targetRole: 'Target role',
    readyToAnalyse: '✓ Ready to analyze',
    completeFieldsAbove: 'Complete the fields above to continue',
    runningAnalysis: 'Running analysis…',
    runAnalysis: 'Run Analysis',
    analyzeAnother: 'Analyze another',
  },

  // ── Coachee detail page ─────────────────────────────────────────────────────
  coacheeDetail: {
    activeExperiment: 'Active Experiment',
    noActiveExperiment: 'No active experiment.',
    suggestedExperiments: 'Suggested Experiments',
    inQueue: (n: number) => `${n} in queue`,
    coacheeCanAccept: 'The coachee can accept one of these from their dashboard when ready.',
    baselinePack: 'Baseline Analysis',
    status: 'Status',
    recentRuns: 'Recent Analyses',
    coacheeNotFound: 'Coachee not found.',
    progressTitle: 'Pattern Trends',
    noProgressYet: 'No pattern data yet. Analyses will populate trends here.',
    pastExperiments: 'Past Experiments',
    noPastExperiments: 'No completed or parked experiments yet.',
    baselineNotStarted: 'Baseline not started.',
    viewRunDetails: 'View details',
    gateFailLabel: 'Quality check failed',
    backToDashboard: '← Back to dashboard',
    analyzeForCoachee: 'Run Analysis',
    noRuns: 'No analyses yet.',
  },

  // ── Coach dashboard cards ─────────────────────────────────────────────────
  coachCard: {
    noBaseline: 'No baseline',
    baselineBuilding: 'Baseline building',
    baselineReady: 'Baseline ready',
    experimenting: 'Experimenting',
    noActivity: 'No activity yet',
    lastAnalysis: (daysAgo: number) =>
      daysAgo === 0 ? 'Today' : daysAgo === 1 ? '1 day ago' : `${daysAgo}d ago`,
    noAnalyses: 'No analyses',
    attempts: (n: number) => `${n} attempt${n !== 1 ? 's' : ''}`,
  },

  // ── Admin page ──────────────────────────────────────────────────────────────
  admin: {
    heading: 'User Management',
    userColumn: 'User',
    roleColumn: 'Role',
    lastLoginColumn: 'Last Login',
    promoteToCoach: 'Promote to Coach',
  },

  // ── Onboarding ────────────────────────────────────────────────────────────
  onboarding: {
    // Welcome page
    welcomeHeading: 'Welcome to ClearVoice',
    welcomeSubheading: 'AI-powered coaching rooted in your actual meetings.',
    welcomeIntro:
      'ClearVoice analyzes your meeting transcripts and gives you personalized coaching feedback — then helps you build better communication habits through small, trackable experiments.',

    journeyHeading: 'How it works',
    journeyStep1Title: 'Build your baseline',
    journeyStep1Desc:
      'Upload three past meeting transcripts so the AI can map your current communication patterns.',
    journeyStep2Title: 'Analyze a meeting',
    journeyStep2Desc:
      'Upload a new transcript and receive personalized coaching feedback with concrete observations.',
    journeyStep3Title: 'Run an experiment',
    journeyStep3Desc:
      'Accept a micro-experiment — a small behavioral change to try in your next meetings.',
    journeyStep4Title: 'Track your growth',
    journeyStep4Desc:
      'Each time you analyze a meeting, the AI checks your progress and your pattern scores update over time.',

    expectHeading: 'What to expect',
    expectItem1: 'Each analysis takes about 30–60 seconds.',
    expectItem2: 'Feedback is based on what you actually said — not generic advice.',
    expectItem3: 'Experiments are small and specific, designed to build one habit at a time.',

    getStarted: 'Get started',
    skip: 'Skip intro',

    // Contextual tips
    tipDismissLabel: 'Dismiss',
    tipBaselineNew:
      'Upload three past meeting transcripts to build your communication baseline. This gives the AI a starting picture of your patterns.',
    tipAnalyze:
      'Upload a meeting transcript and the AI will give you personalized coaching feedback plus a micro-experiment to try.',
    tipExperiment:
      'This is where you track your active experiment. After each meeting analysis, the AI checks whether you tried it.',
    tipProgress:
      'Your pattern scores over time. Trends become visible after three or more analyzed meetings.',

    // Sidebar replay
    replayOnboarding: 'Replay intro',
  },
} as const;
