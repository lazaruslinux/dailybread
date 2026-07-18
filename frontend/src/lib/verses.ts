// The daily verse, bundled with the app so it needs no network and works
// offline. Text is the New King James Version, quoted under Thomas Nelson's
// gratis quotation policy (fewer than 500 verses, scripture is a small
// fraction of the work, notice included). The required copyright notice
// ships in the Me tab and the README; the verse text below is NOT covered
// by this project's AGPL-3.0 license.
//
// Curation: morning encouragement, weighted toward the New Testament and
// the words of Jesus, with a handful of beloved Psalms and prophets.
//
// `usfm` is Bible.com's passage id ("MAT.6.11", ranges like "PRO.3.5-6").
// The list is in rough canonical order and rotates by day of year, so the
// whole family sees the same verse on the same calendar day.

export interface Verse {
  ref: string
  text: string
  usfm: string
}

const NKJV_VERSION_ID = 114

export function verseLink(verse: Verse): string {
  return `https://www.bible.com/bible/${NKJV_VERSION_ID}/${verse.usfm}.NKJV`
}

// Day of year (Jan 1 = 1) from calendar parts, immune to DST hour shifts.
function dayOfYear(d: Date): number {
  const utcDay = Date.UTC(d.getFullYear(), d.getMonth(), d.getDate())
  const utcJan1 = Date.UTC(d.getFullYear(), 0, 1)
  return Math.floor((utcDay - utcJan1) / 86_400_000) + 1
}

export function verseForDate(d: Date): Verse {
  return VERSES[(dayOfYear(d) - 1) % VERSES.length]
}

// A small set of verses for one day: the day's verse plus a couple more,
// spread across the collection so they feel varied. Deterministic from the
// date, so the whole family can browse the same three and land on the same
// one. verseForDate stays the first of these.
export function versesForDate(d: Date, n = 3): Verse[] {
  const len = VERSES.length
  const base = (dayOfYear(d) - 1) % len
  const stride = Math.floor(len / n) || 1
  return Array.from({ length: n }, (_, i) => VERSES[(base + i * stride) % len])
}

// First entry lands on January 1: the verse the app is named for.
export const VERSES: Verse[] = [
  {
    ref: 'Matthew 6:11',
    text: 'Give us this day our daily bread.',
    usfm: 'MAT.6.11',
  },
  {
    ref: 'Numbers 6:24-26',
    text: 'The LORD bless you and keep you; The LORD make His face shine upon you, And be gracious to you; The LORD lift up His countenance upon you, And give you peace.',
    usfm: 'NUM.6.24-26',
  },
  {
    ref: 'Deuteronomy 31:6',
    text: 'Be strong and of good courage, do not fear nor be afraid of them; for the LORD your God, He is the One who goes with you. He will not leave you nor forsake you.',
    usfm: 'DEU.31.6',
  },
  {
    ref: 'Joshua 1:9',
    text: 'Have I not commanded you? Be strong and of good courage; do not be afraid, nor be dismayed, for the LORD your God is with you wherever you go.',
    usfm: 'JOS.1.9',
  },
  {
    ref: 'Psalm 5:3',
    text: 'My voice You shall hear in the morning, O LORD; In the morning I will direct it to You, And I will look up.',
    usfm: 'PSA.5.3',
  },
  {
    ref: 'Psalm 16:11',
    text: 'You will show me the path of life; In Your presence is fullness of joy; At Your right hand are pleasures forevermore.',
    usfm: 'PSA.16.11',
  },
  {
    ref: 'Psalm 23:1',
    text: 'The LORD is my shepherd; I shall not want.',
    usfm: 'PSA.23.1',
  },
  {
    ref: 'Psalm 28:7',
    text: 'The LORD is my strength and my shield; My heart trusted in Him, and I am helped; Therefore my heart greatly rejoices, And with my song I will praise Him.',
    usfm: 'PSA.28.7',
  },
  {
    ref: 'Psalm 34:8',
    text: 'Oh, taste and see that the LORD is good; Blessed is the man who trusts in Him!',
    usfm: 'PSA.34.8',
  },
  {
    ref: 'Psalm 37:4',
    text: 'Delight yourself also in the LORD, And He shall give you the desires of your heart.',
    usfm: 'PSA.37.4',
  },
  {
    ref: 'Psalm 46:10',
    text: 'Be still, and know that I am God; I will be exalted among the nations, I will be exalted in the earth!',
    usfm: 'PSA.46.10',
  },
  {
    ref: 'Psalm 90:14',
    text: 'Oh, satisfy us early with Your mercy, That we may rejoice and be glad all our days!',
    usfm: 'PSA.90.14',
  },
  {
    ref: 'Psalm 118:24',
    text: 'This is the day the LORD has made; We will rejoice and be glad in it.',
    usfm: 'PSA.118.24',
  },
  {
    ref: 'Psalm 119:105',
    text: 'Your word is a lamp to my feet And a light to my path.',
    usfm: 'PSA.119.105',
  },
  {
    ref: 'Psalm 121:1-2',
    text: 'I will lift up my eyes to the hills—From whence comes my help? My help comes from the LORD, Who made heaven and earth.',
    usfm: 'PSA.121.1-2',
  },
  {
    ref: 'Psalm 143:8',
    text: 'Cause me to hear Your lovingkindness in the morning, For in You do I trust; Cause me to know the way in which I should walk, For I lift up my soul to You.',
    usfm: 'PSA.143.8',
  },
  {
    ref: 'Proverbs 3:5-6',
    text: 'Trust in the LORD with all your heart, And lean not on your own understanding; In all your ways acknowledge Him, And He shall direct your paths.',
    usfm: 'PRO.3.5-6',
  },
  {
    ref: 'Proverbs 16:3',
    text: 'Commit your works to the LORD, And your thoughts will be established.',
    usfm: 'PRO.16.3',
  },
  {
    ref: 'Isaiah 26:3',
    text: 'You will keep him in perfect peace, Whose mind is stayed on You, Because he trusts in You.',
    usfm: 'ISA.26.3',
  },
  {
    ref: 'Isaiah 40:31',
    text: 'But those who wait on the LORD Shall renew their strength; They shall mount up with wings like eagles, They shall run and not be weary, They shall walk and not faint.',
    usfm: 'ISA.40.31',
  },
  {
    ref: 'Isaiah 41:10',
    text: 'Fear not, for I am with you; Be not dismayed, for I am your God. I will strengthen you, Yes, I will help you, I will uphold you with My righteous right hand.',
    usfm: 'ISA.41.10',
  },
  {
    ref: 'Jeremiah 29:11',
    text: 'For I know the thoughts that I think toward you, says the LORD, thoughts of peace and not of evil, to give you a future and a hope.',
    usfm: 'JER.29.11',
  },
  {
    ref: 'Lamentations 3:22-23',
    text: "Through the LORD's mercies we are not consumed, Because His compassions fail not. They are new every morning; Great is Your faithfulness.",
    usfm: 'LAM.3.22-23',
  },
  {
    ref: 'Micah 6:8',
    text: 'He has shown you, O man, what is good; And what does the LORD require of you But to do justly, To love mercy, And to walk humbly with your God?',
    usfm: 'MIC.6.8',
  },
  {
    ref: 'Zephaniah 3:17',
    text: 'The LORD your God in your midst, The Mighty One, will save; He will rejoice over you with gladness, He will quiet you with His love, He will rejoice over you with singing.',
    usfm: 'ZEP.3.17',
  },
  {
    ref: 'Matthew 4:4',
    text: "It is written, 'Man shall not live by bread alone, but by every word that proceeds from the mouth of God.'",
    usfm: 'MAT.4.4',
  },
  {
    ref: 'Matthew 5:6',
    text: 'Blessed are those who hunger and thirst for righteousness, For they shall be filled.',
    usfm: 'MAT.5.6',
  },
  {
    ref: 'Matthew 5:8',
    text: 'Blessed are the pure in heart, For they shall see God.',
    usfm: 'MAT.5.8',
  },
  {
    ref: 'Matthew 5:9',
    text: 'Blessed are the peacemakers, For they shall be called sons of God.',
    usfm: 'MAT.5.9',
  },
  {
    ref: 'Matthew 5:14',
    text: 'You are the light of the world. A city that is set on a hill cannot be hidden.',
    usfm: 'MAT.5.14',
  },
  {
    ref: 'Matthew 5:16',
    text: 'Let your light so shine before men, that they may see your good works and glorify your Father in heaven.',
    usfm: 'MAT.5.16',
  },
  {
    ref: 'Matthew 6:21',
    text: 'For where your treasure is, there your heart will be also.',
    usfm: 'MAT.6.21',
  },
  {
    ref: 'Matthew 6:26',
    text: 'Look at the birds of the air, for they neither sow nor reap nor gather into barns; yet your heavenly Father feeds them. Are you not of more value than they?',
    usfm: 'MAT.6.26',
  },
  {
    ref: 'Matthew 6:33',
    text: 'But seek first the kingdom of God and His righteousness, and all these things shall be added to you.',
    usfm: 'MAT.6.33',
  },
  {
    ref: 'Matthew 6:34',
    text: 'Therefore do not worry about tomorrow, for tomorrow will worry about its own things. Sufficient for the day is its own trouble.',
    usfm: 'MAT.6.34',
  },
  {
    ref: 'Matthew 7:7',
    text: 'Ask, and it will be given to you; seek, and you will find; knock, and it will be opened to you.',
    usfm: 'MAT.7.7',
  },
  {
    ref: 'Matthew 7:12',
    text: 'Therefore, whatever you want men to do to you, do also to them, for this is the Law and the Prophets.',
    usfm: 'MAT.7.12',
  },
  {
    ref: 'Matthew 11:28-30',
    text: 'Come to Me, all you who labor and are heavy laden, and I will give you rest. Take My yoke upon you and learn from Me, for I am gentle and lowly in heart, and you will find rest for your souls. For My yoke is easy and My burden is light.',
    usfm: 'MAT.11.28-30',
  },
  {
    ref: 'Matthew 17:20',
    text: "If you have faith as a mustard seed, you will say to this mountain, 'Move from here to there,' and it will move; and nothing will be impossible for you.",
    usfm: 'MAT.17.20',
  },
  {
    ref: 'Matthew 18:20',
    text: 'For where two or three are gathered together in My name, I am there in the midst of them.',
    usfm: 'MAT.18.20',
  },
  {
    ref: 'Matthew 19:14',
    text: 'Let the little children come to Me, and do not forbid them; for of such is the kingdom of heaven.',
    usfm: 'MAT.19.14',
  },
  {
    ref: 'Matthew 19:26',
    text: 'With men this is impossible, but with God all things are possible.',
    usfm: 'MAT.19.26',
  },
  {
    ref: 'Matthew 22:37-39',
    text: 'You shall love the Lord your God with all your heart, with all your soul, and with all your mind. This is the first and great commandment. And the second is like it: You shall love your neighbor as yourself.',
    usfm: 'MAT.22.37-39',
  },
  {
    ref: 'Matthew 28:20',
    text: 'Lo, I am with you always, even to the end of the age.',
    usfm: 'MAT.28.20',
  },
  {
    ref: 'Mark 9:23',
    text: 'If you can believe, all things are possible to him who believes.',
    usfm: 'MRK.9.23',
  },
  {
    ref: 'Mark 11:24',
    text: 'Therefore I say to you, whatever things you ask when you pray, believe that you receive them, and you will have them.',
    usfm: 'MRK.11.24',
  },
  {
    ref: 'Luke 1:37',
    text: 'For with God nothing will be impossible.',
    usfm: 'LUK.1.37',
  },
  {
    ref: 'Luke 6:38',
    text: 'Give, and it will be given to you: good measure, pressed down, shaken together, and running over will be put into your bosom.',
    usfm: 'LUK.6.38',
  },
  {
    ref: 'Luke 12:7',
    text: 'But the very hairs of your head are all numbered. Do not fear therefore; you are of more value than many sparrows.',
    usfm: 'LUK.12.7',
  },
  {
    ref: 'Luke 12:32',
    text: "Do not fear, little flock, for it is your Father's good pleasure to give you the kingdom.",
    usfm: 'LUK.12.32',
  },
  {
    ref: 'John 3:16',
    text: 'For God so loved the world that He gave His only begotten Son, that whoever believes in Him should not perish but have everlasting life.',
    usfm: 'JHN.3.16',
  },
  {
    ref: 'John 4:14',
    text: 'Whoever drinks of the water that I shall give him will never thirst. But the water that I shall give him will become in him a fountain of water springing up into everlasting life.',
    usfm: 'JHN.4.14',
  },
  {
    ref: 'John 6:35',
    text: 'I am the bread of life. He who comes to Me shall never hunger, and he who believes in Me shall never thirst.',
    usfm: 'JHN.6.35',
  },
  {
    ref: 'John 8:12',
    text: 'I am the light of the world. He who follows Me shall not walk in darkness, but have the light of life.',
    usfm: 'JHN.8.12',
  },
  {
    ref: 'John 8:32',
    text: 'And you shall know the truth, and the truth shall make you free.',
    usfm: 'JHN.8.32',
  },
  {
    ref: 'John 10:10',
    text: 'I have come that they may have life, and that they may have it more abundantly.',
    usfm: 'JHN.10.10',
  },
  {
    ref: 'John 11:25',
    text: 'I am the resurrection and the life. He who believes in Me, though he may die, he shall live.',
    usfm: 'JHN.11.25',
  },
  {
    ref: 'John 13:34',
    text: 'A new commandment I give to you, that you love one another; as I have loved you, that you also love one another.',
    usfm: 'JHN.13.34',
  },
  {
    ref: 'John 13:35',
    text: 'By this all will know that you are My disciples, if you have love for one another.',
    usfm: 'JHN.13.35',
  },
  {
    ref: 'John 14:1',
    text: 'Let not your heart be troubled; you believe in God, believe also in Me.',
    usfm: 'JHN.14.1',
  },
  {
    ref: 'John 14:6',
    text: 'I am the way, the truth, and the life. No one comes to the Father except through Me.',
    usfm: 'JHN.14.6',
  },
  {
    ref: 'John 14:27',
    text: 'Peace I leave with you, My peace I give to you; not as the world gives do I give to you. Let not your heart be troubled, neither let it be afraid.',
    usfm: 'JHN.14.27',
  },
  {
    ref: 'John 15:5',
    text: 'I am the vine, you are the branches. He who abides in Me, and I in him, bears much fruit; for without Me you can do nothing.',
    usfm: 'JHN.15.5',
  },
  {
    ref: 'John 15:11',
    text: 'These things I have spoken to you, that My joy may remain in you, and that your joy may be full.',
    usfm: 'JHN.15.11',
  },
  {
    ref: 'John 16:33',
    text: 'These things I have spoken to you, that in Me you may have peace. In the world you will have tribulation; but be of good cheer, I have overcome the world.',
    usfm: 'JHN.16.33',
  },
  {
    ref: 'Romans 8:28',
    text: 'And we know that all things work together for good to those who love God, to those who are the called according to His purpose.',
    usfm: 'ROM.8.28',
  },
  {
    ref: 'Romans 8:31',
    text: 'What then shall we say to these things? If God is for us, who can be against us?',
    usfm: 'ROM.8.31',
  },
  {
    ref: 'Romans 8:37',
    text: 'Yet in all these things we are more than conquerors through Him who loved us.',
    usfm: 'ROM.8.37',
  },
  {
    ref: 'Romans 12:2',
    text: 'And do not be conformed to this world, but be transformed by the renewing of your mind, that you may prove what is that good and acceptable and perfect will of God.',
    usfm: 'ROM.12.2',
  },
  {
    ref: 'Romans 12:12',
    text: 'Rejoicing in hope, patient in tribulation, continuing steadfastly in prayer.',
    usfm: 'ROM.12.12',
  },
  {
    ref: 'Romans 12:21',
    text: 'Do not be overcome by evil, but overcome evil with good.',
    usfm: 'ROM.12.21',
  },
  {
    ref: 'Romans 15:13',
    text: 'Now may the God of hope fill you with all joy and peace in believing, that you may abound in hope by the power of the Holy Spirit.',
    usfm: 'ROM.15.13',
  },
  {
    ref: '1 Corinthians 10:31',
    text: 'Therefore, whether you eat or drink, or whatever you do, do all to the glory of God.',
    usfm: '1CO.10.31',
  },
  {
    ref: '1 Corinthians 13:4',
    text: 'Love suffers long and is kind; love does not envy; love does not parade itself, is not puffed up.',
    usfm: '1CO.13.4',
  },
  {
    ref: '1 Corinthians 16:13-14',
    text: 'Watch, stand fast in the faith, be brave, be strong. Let all that you do be done with love.',
    usfm: '1CO.16.13-14',
  },
  {
    ref: '2 Corinthians 4:16',
    text: 'Therefore we do not lose heart. Even though our outward man is perishing, yet the inward man is being renewed day by day.',
    usfm: '2CO.4.16',
  },
  {
    ref: '2 Corinthians 5:7',
    text: 'For we walk by faith, not by sight.',
    usfm: '2CO.5.7',
  },
  {
    ref: '2 Corinthians 5:17',
    text: 'Therefore, if anyone is in Christ, he is a new creation; old things have passed away; behold, all things have become new.',
    usfm: '2CO.5.17',
  },
  {
    ref: '2 Corinthians 12:9',
    text: 'My grace is sufficient for you, for My strength is made perfect in weakness.',
    usfm: '2CO.12.9',
  },
  {
    ref: 'Galatians 5:22-23',
    text: 'But the fruit of the Spirit is love, joy, peace, longsuffering, kindness, goodness, faithfulness, gentleness, self-control. Against such there is no law.',
    usfm: 'GAL.5.22-23',
  },
  {
    ref: 'Galatians 6:9',
    text: 'And let us not grow weary while doing good, for in due season we shall reap if we do not lose heart.',
    usfm: 'GAL.6.9',
  },
  {
    ref: 'Ephesians 2:10',
    text: 'For we are His workmanship, created in Christ Jesus for good works, which God prepared beforehand that we should walk in them.',
    usfm: 'EPH.2.10',
  },
  {
    ref: 'Ephesians 3:20',
    text: 'Now to Him who is able to do exceedingly abundantly above all that we ask or think, according to the power that works in us.',
    usfm: 'EPH.3.20',
  },
  {
    ref: 'Ephesians 4:32',
    text: 'And be kind to one another, tenderhearted, forgiving one another, even as God in Christ forgave you.',
    usfm: 'EPH.4.32',
  },
  {
    ref: 'Ephesians 6:10',
    text: 'Finally, my brethren, be strong in the Lord and in the power of His might.',
    usfm: 'EPH.6.10',
  },
  {
    ref: 'Philippians 1:6',
    text: 'Being confident of this very thing, that He who has begun a good work in you will complete it until the day of Jesus Christ.',
    usfm: 'PHP.1.6',
  },
  {
    ref: 'Philippians 2:14',
    text: 'Do all things without complaining and disputing.',
    usfm: 'PHP.2.14',
  },
  {
    ref: 'Philippians 4:4',
    text: 'Rejoice in the Lord always. Again I will say, rejoice!',
    usfm: 'PHP.4.4',
  },
  {
    ref: 'Philippians 4:6-7',
    text: 'Be anxious for nothing, but in everything by prayer and supplication, with thanksgiving, let your requests be made known to God; and the peace of God, which surpasses all understanding, will guard your hearts and minds through Christ Jesus.',
    usfm: 'PHP.4.6-7',
  },
  {
    ref: 'Philippians 4:8',
    text: 'Finally, brethren, whatever things are true, whatever things are noble, whatever things are just, whatever things are pure, whatever things are lovely, whatever things are of good report, if there is any virtue and if there is anything praiseworthy—meditate on these things.',
    usfm: 'PHP.4.8',
  },
  {
    ref: 'Philippians 4:13',
    text: 'I can do all things through Christ who strengthens me.',
    usfm: 'PHP.4.13',
  },
  {
    ref: 'Colossians 3:2',
    text: 'Set your mind on things above, not on things on the earth.',
    usfm: 'COL.3.2',
  },
  {
    ref: 'Colossians 3:23',
    text: 'And whatever you do, do it heartily, as to the Lord and not to men.',
    usfm: 'COL.3.23',
  },
  {
    ref: '1 Thessalonians 5:16-18',
    text: 'Rejoice always, pray without ceasing, in everything give thanks; for this is the will of God in Christ Jesus for you.',
    usfm: '1TH.5.16-18',
  },
  {
    ref: '2 Timothy 1:7',
    text: 'For God has not given us a spirit of fear, but of power and of love and of a sound mind.',
    usfm: '2TI.1.7',
  },
  {
    ref: 'Hebrews 11:1',
    text: 'Now faith is the substance of things hoped for, the evidence of things not seen.',
    usfm: 'HEB.11.1',
  },
  {
    ref: 'Hebrews 12:1',
    text: 'Let us lay aside every weight, and the sin which so easily ensnares us, and let us run with endurance the race that is set before us.',
    usfm: 'HEB.12.1',
  },
  {
    ref: 'Hebrews 13:5',
    text: "For He Himself has said, 'I will never leave you nor forsake you.'",
    usfm: 'HEB.13.5',
  },
  {
    ref: 'Hebrews 13:8',
    text: 'Jesus Christ is the same yesterday, today, and forever.',
    usfm: 'HEB.13.8',
  },
  {
    ref: 'James 1:5',
    text: 'If any of you lacks wisdom, let him ask of God, who gives to all liberally and without reproach, and it will be given to him.',
    usfm: 'JAS.1.5',
  },
  {
    ref: 'James 1:17',
    text: 'Every good gift and every perfect gift is from above, and comes down from the Father of lights, with whom there is no variation or shadow of turning.',
    usfm: 'JAS.1.17',
  },
  {
    ref: 'James 1:22',
    text: 'But be doers of the word, and not hearers only, deceiving yourselves.',
    usfm: 'JAS.1.22',
  },
  {
    ref: '1 Peter 5:7',
    text: 'Casting all your care upon Him, for He cares for you.',
    usfm: '1PE.5.7',
  },
  {
    ref: '1 John 4:4',
    text: 'You are of God, little children, and have overcome them, because He who is in you is greater than he who is in the world.',
    usfm: '1JN.4.4',
  },
  {
    ref: '1 John 4:19',
    text: 'We love Him because He first loved us.',
    usfm: '1JN.4.19',
  },
  {
    ref: 'Revelation 3:20',
    text: 'Behold, I stand at the door and knock. If anyone hears My voice and opens the door, I will come in to him and dine with him, and he with Me.',
    usfm: 'REV.3.20',
  },
  {
    ref: 'Revelation 21:5',
    text: 'Behold, I make all things new.',
    usfm: 'REV.21.5',
  },
]
