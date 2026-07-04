// The daily verse, bundled with the app so it needs no network and works
// offline. Text is the King James Version (public domain); the tap-through
// link opens the same passage on Bible.com in the NKJV, whose text is
// copyrighted and can't ship inside the app.
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

// First entry lands on January 1: the verse the app is named for.
export const VERSES: Verse[] = [
  {
    ref: 'Matthew 6:11',
    text: 'Give us this day our daily bread.',
    usfm: 'MAT.6.11',
  },
  {
    ref: 'Genesis 1:1',
    text: 'In the beginning God created the heaven and the earth.',
    usfm: 'GEN.1.1',
  },
  {
    ref: 'Numbers 6:24-26',
    text: 'The LORD bless thee, and keep thee: the LORD make his face shine upon thee, and be gracious unto thee: the LORD lift up his countenance upon thee, and give thee peace.',
    usfm: 'NUM.6.24-26',
  },
  {
    ref: 'Deuteronomy 31:6',
    text: 'Be strong and of a good courage, fear not, nor be afraid of them: for the LORD thy God, he it is that doth go with thee; he will not fail thee, nor forsake thee.',
    usfm: 'DEU.31.6',
  },
  {
    ref: 'Joshua 1:9',
    text: 'Have not I commanded thee? Be strong and of a good courage; be not afraid, neither be thou dismayed: for the LORD thy God is with thee whithersoever thou goest.',
    usfm: 'JOS.1.9',
  },
  {
    ref: 'Joshua 24:15',
    text: 'Choose you this day whom ye will serve... but as for me and my house, we will serve the LORD.',
    usfm: 'JOS.24.15',
  },
  {
    ref: '1 Samuel 16:7',
    text: 'For the LORD seeth not as man seeth; for man looketh on the outward appearance, but the LORD looketh on the heart.',
    usfm: '1SA.16.7',
  },
  {
    ref: '1 Chronicles 16:11',
    text: 'Seek the LORD and his strength, seek his face continually.',
    usfm: '1CH.16.11',
  },
  {
    ref: 'Psalm 4:8',
    text: 'I will both lay me down in peace, and sleep: for thou, LORD, only makest me dwell in safety.',
    usfm: 'PSA.4.8',
  },
  {
    ref: 'Psalm 16:11',
    text: 'Thou wilt shew me the path of life: in thy presence is fulness of joy; at thy right hand there are pleasures for evermore.',
    usfm: 'PSA.16.11',
  },
  {
    ref: 'Psalm 18:2',
    text: 'The LORD is my rock, and my fortress, and my deliverer; my God, my strength, in whom I will trust.',
    usfm: 'PSA.18.2',
  },
  {
    ref: 'Psalm 19:14',
    text: 'Let the words of my mouth, and the meditation of my heart, be acceptable in thy sight, O LORD, my strength, and my redeemer.',
    usfm: 'PSA.19.14',
  },
  {
    ref: 'Psalm 23:1',
    text: 'The LORD is my shepherd; I shall not want.',
    usfm: 'PSA.23.1',
  },
  {
    ref: 'Psalm 27:1',
    text: 'The LORD is my light and my salvation; whom shall I fear? the LORD is the strength of my life; of whom shall I be afraid?',
    usfm: 'PSA.27.1',
  },
  {
    ref: 'Psalm 28:7',
    text: 'The LORD is my strength and my shield; my heart trusted in him, and I am helped: therefore my heart greatly rejoiceth; and with my song will I praise him.',
    usfm: 'PSA.28.7',
  },
  {
    ref: 'Psalm 30:5',
    text: 'For his anger endureth but a moment; in his favour is life: weeping may endure for a night, but joy cometh in the morning.',
    usfm: 'PSA.30.5',
  },
  {
    ref: 'Psalm 34:8',
    text: 'O taste and see that the LORD is good: blessed is the man that trusteth in him.',
    usfm: 'PSA.34.8',
  },
  {
    ref: 'Psalm 34:18',
    text: 'The LORD is nigh unto them that are of a broken heart; and saveth such as be of a contrite spirit.',
    usfm: 'PSA.34.18',
  },
  {
    ref: 'Psalm 37:4',
    text: 'Delight thyself also in the LORD; and he shall give thee the desires of thine heart.',
    usfm: 'PSA.37.4',
  },
  {
    ref: 'Psalm 46:1',
    text: 'God is our refuge and strength, a very present help in trouble.',
    usfm: 'PSA.46.1',
  },
  {
    ref: 'Psalm 46:10',
    text: 'Be still, and know that I am God: I will be exalted among the heathen, I will be exalted in the earth.',
    usfm: 'PSA.46.10',
  },
  {
    ref: 'Psalm 51:10',
    text: 'Create in me a clean heart, O God; and renew a right spirit within me.',
    usfm: 'PSA.51.10',
  },
  {
    ref: 'Psalm 55:22',
    text: 'Cast thy burden upon the LORD, and he shall sustain thee: he shall never suffer the righteous to be moved.',
    usfm: 'PSA.55.22',
  },
  {
    ref: 'Psalm 56:3',
    text: 'What time I am afraid, I will trust in thee.',
    usfm: 'PSA.56.3',
  },
  {
    ref: 'Psalm 62:1',
    text: 'Truly my soul waiteth upon God: from him cometh my salvation.',
    usfm: 'PSA.62.1',
  },
  {
    ref: 'Psalm 73:26',
    text: 'My flesh and my heart faileth: but God is the strength of my heart, and my portion for ever.',
    usfm: 'PSA.73.26',
  },
  {
    ref: 'Psalm 86:5',
    text: 'For thou, Lord, art good, and ready to forgive; and plenteous in mercy unto all them that call upon thee.',
    usfm: 'PSA.86.5',
  },
  {
    ref: 'Psalm 90:12',
    text: 'So teach us to number our days, that we may apply our hearts unto wisdom.',
    usfm: 'PSA.90.12',
  },
  {
    ref: 'Psalm 91:1',
    text: 'He that dwelleth in the secret place of the most High shall abide under the shadow of the Almighty.',
    usfm: 'PSA.91.1',
  },
  {
    ref: 'Psalm 94:19',
    text: 'In the multitude of my thoughts within me thy comforts delight my soul.',
    usfm: 'PSA.94.19',
  },
  {
    ref: 'Psalm 100:5',
    text: 'For the LORD is good; his mercy is everlasting; and his truth endureth to all generations.',
    usfm: 'PSA.100.5',
  },
  {
    ref: 'Psalm 103:1',
    text: 'Bless the LORD, O my soul: and all that is within me, bless his holy name.',
    usfm: 'PSA.103.1',
  },
  {
    ref: 'Psalm 118:24',
    text: 'This is the day which the LORD hath made; we will rejoice and be glad in it.',
    usfm: 'PSA.118.24',
  },
  {
    ref: 'Psalm 119:105',
    text: 'Thy word is a lamp unto my feet, and a light unto my path.',
    usfm: 'PSA.119.105',
  },
  {
    ref: 'Psalm 121:1-2',
    text: 'I will lift up mine eyes unto the hills, from whence cometh my help. My help cometh from the LORD, which made heaven and earth.',
    usfm: 'PSA.121.1-2',
  },
  {
    ref: 'Psalm 127:1',
    text: 'Except the LORD build the house, they labour in vain that build it: except the LORD keep the city, the watchman waketh but in vain.',
    usfm: 'PSA.127.1',
  },
  {
    ref: 'Psalm 133:1',
    text: 'Behold, how good and how pleasant it is for brethren to dwell together in unity!',
    usfm: 'PSA.133.1',
  },
  {
    ref: 'Psalm 136:1',
    text: 'O give thanks unto the LORD; for he is good: for his mercy endureth for ever.',
    usfm: 'PSA.136.1',
  },
  {
    ref: 'Psalm 139:14',
    text: 'I will praise thee; for I am fearfully and wonderfully made: marvellous are thy works; and that my soul knoweth right well.',
    usfm: 'PSA.139.14',
  },
  {
    ref: 'Psalm 143:8',
    text: 'Cause me to hear thy lovingkindness in the morning; for in thee do I trust: cause me to know the way wherein I should walk; for I lift up my soul unto thee.',
    usfm: 'PSA.143.8',
  },
  {
    ref: 'Psalm 147:3',
    text: 'He healeth the broken in heart, and bindeth up their wounds.',
    usfm: 'PSA.147.3',
  },
  {
    ref: 'Psalm 150:6',
    text: 'Let every thing that hath breath praise the LORD. Praise ye the LORD.',
    usfm: 'PSA.150.6',
  },
  {
    ref: 'Proverbs 3:5-6',
    text: 'Trust in the LORD with all thine heart; and lean not unto thine own understanding. In all thy ways acknowledge him, and he shall direct thy paths.',
    usfm: 'PRO.3.5-6',
  },
  {
    ref: 'Proverbs 15:1',
    text: 'A soft answer turneth away wrath: but grievous words stir up anger.',
    usfm: 'PRO.15.1',
  },
  {
    ref: 'Proverbs 16:3',
    text: 'Commit thy works unto the LORD, and thy thoughts shall be established.',
    usfm: 'PRO.16.3',
  },
  {
    ref: 'Proverbs 16:24',
    text: 'Pleasant words are as an honeycomb, sweet to the soul, and health to the bones.',
    usfm: 'PRO.16.24',
  },
  {
    ref: 'Proverbs 17:22',
    text: 'A merry heart doeth good like a medicine: but a broken spirit drieth the bones.',
    usfm: 'PRO.17.22',
  },
  {
    ref: 'Proverbs 18:10',
    text: 'The name of the LORD is a strong tower: the righteous runneth into it, and is safe.',
    usfm: 'PRO.18.10',
  },
  {
    ref: 'Proverbs 22:6',
    text: 'Train up a child in the way he should go: and when he is old, he will not depart from it.',
    usfm: 'PRO.22.6',
  },
  {
    ref: 'Proverbs 27:17',
    text: 'Iron sharpeneth iron; so a man sharpeneth the countenance of his friend.',
    usfm: 'PRO.27.17',
  },
  {
    ref: 'Ecclesiastes 3:1',
    text: 'To every thing there is a season, and a time to every purpose under the heaven.',
    usfm: 'ECC.3.1',
  },
  {
    ref: 'Ecclesiastes 4:9',
    text: 'Two are better than one; because they have a good reward for their labour.',
    usfm: 'ECC.4.9',
  },
  {
    ref: 'Isaiah 9:6',
    text: 'For unto us a child is born, unto us a son is given: and the government shall be upon his shoulder: and his name shall be called Wonderful, Counsellor, The mighty God, The everlasting Father, The Prince of Peace.',
    usfm: 'ISA.9.6',
  },
  {
    ref: 'Isaiah 12:2',
    text: 'Behold, God is my salvation; I will trust, and not be afraid: for the LORD JEHOVAH is my strength and my song; he also is become my salvation.',
    usfm: 'ISA.12.2',
  },
  {
    ref: 'Isaiah 26:3',
    text: 'Thou wilt keep him in perfect peace, whose mind is stayed on thee: because he trusteth in thee.',
    usfm: 'ISA.26.3',
  },
  {
    ref: 'Isaiah 40:8',
    text: 'The grass withereth, the flower fadeth: but the word of our God shall stand for ever.',
    usfm: 'ISA.40.8',
  },
  {
    ref: 'Isaiah 40:31',
    text: 'But they that wait upon the LORD shall renew their strength; they shall mount up with wings as eagles; they shall run, and not be weary; and they shall walk, and not faint.',
    usfm: 'ISA.40.31',
  },
  {
    ref: 'Isaiah 41:10',
    text: 'Fear thou not; for I am with thee: be not dismayed; for I am thy God: I will strengthen thee; yea, I will help thee; yea, I will uphold thee with the right hand of my righteousness.',
    usfm: 'ISA.41.10',
  },
  {
    ref: 'Isaiah 43:2',
    text: 'When thou passest through the waters, I will be with thee; and through the rivers, they shall not overflow thee.',
    usfm: 'ISA.43.2',
  },
  {
    ref: 'Isaiah 53:5',
    text: 'But he was wounded for our transgressions, he was bruised for our iniquities: the chastisement of our peace was upon him; and with his stripes we are healed.',
    usfm: 'ISA.53.5',
  },
  {
    ref: 'Isaiah 55:6',
    text: 'Seek ye the LORD while he may be found, call ye upon him while he is near.',
    usfm: 'ISA.55.6',
  },
  {
    ref: 'Jeremiah 29:11',
    text: 'For I know the thoughts that I think toward you, saith the LORD, thoughts of peace, and not of evil, to give you an expected end.',
    usfm: 'JER.29.11',
  },
  {
    ref: 'Jeremiah 33:3',
    text: 'Call unto me, and I will answer thee, and shew thee great and mighty things, which thou knowest not.',
    usfm: 'JER.33.3',
  },
  {
    ref: 'Lamentations 3:22-23',
    text: "It is of the LORD's mercies that we are not consumed, because his compassions fail not. They are new every morning: great is thy faithfulness.",
    usfm: 'LAM.3.22-23',
  },
  {
    ref: 'Micah 6:8',
    text: 'He hath shewed thee, O man, what is good; and what doth the LORD require of thee, but to do justly, and to love mercy, and to walk humbly with thy God?',
    usfm: 'MIC.6.8',
  },
  {
    ref: 'Nahum 1:7',
    text: 'The LORD is good, a strong hold in the day of trouble; and he knoweth them that trust in him.',
    usfm: 'NAM.1.7',
  },
  {
    ref: 'Zephaniah 3:17',
    text: 'The LORD thy God in the midst of thee is mighty; he will save, he will rejoice over thee with joy; he will rest in his love, he will joy over thee with singing.',
    usfm: 'ZEP.3.17',
  },
  {
    ref: 'Matthew 4:4',
    text: 'It is written, Man shall not live by bread alone, but by every word that proceedeth out of the mouth of God.',
    usfm: 'MAT.4.4',
  },
  {
    ref: 'Matthew 5:6',
    text: 'Blessed are they which do hunger and thirst after righteousness: for they shall be filled.',
    usfm: 'MAT.5.6',
  },
  {
    ref: 'Matthew 5:9',
    text: 'Blessed are the peacemakers: for they shall be called the children of God.',
    usfm: 'MAT.5.9',
  },
  {
    ref: 'Matthew 5:14',
    text: 'Ye are the light of the world. A city that is set on an hill cannot be hid.',
    usfm: 'MAT.5.14',
  },
  {
    ref: 'Matthew 5:16',
    text: 'Let your light so shine before men, that they may see your good works, and glorify your Father which is in heaven.',
    usfm: 'MAT.5.16',
  },
  {
    ref: 'Matthew 6:33',
    text: 'But seek ye first the kingdom of God, and his righteousness; and all these things shall be added unto you.',
    usfm: 'MAT.6.33',
  },
  {
    ref: 'Matthew 6:34',
    text: 'Take therefore no thought for the morrow: for the morrow shall take thought for the things of itself. Sufficient unto the day is the evil thereof.',
    usfm: 'MAT.6.34',
  },
  {
    ref: 'Matthew 7:7',
    text: 'Ask, and it shall be given you; seek, and ye shall find; knock, and it shall be opened unto you.',
    usfm: 'MAT.7.7',
  },
  {
    ref: 'Matthew 11:28',
    text: 'Come unto me, all ye that labour and are heavy laden, and I will give you rest.',
    usfm: 'MAT.11.28',
  },
  {
    ref: 'Matthew 18:20',
    text: 'For where two or three are gathered together in my name, there am I in the midst of them.',
    usfm: 'MAT.18.20',
  },
  {
    ref: 'Matthew 19:26',
    text: 'With men this is impossible; but with God all things are possible.',
    usfm: 'MAT.19.26',
  },
  {
    ref: 'Matthew 22:37-39',
    text: 'Thou shalt love the Lord thy God with all thy heart, and with all thy soul, and with all thy mind... and the second is like unto it, Thou shalt love thy neighbour as thyself.',
    usfm: 'MAT.22.37-39',
  },
  {
    ref: 'Matthew 28:20',
    text: 'Lo, I am with you alway, even unto the end of the world.',
    usfm: 'MAT.28.20',
  },
  {
    ref: 'Mark 9:23',
    text: 'Jesus said unto him, If thou canst believe, all things are possible to him that believeth.',
    usfm: 'MRK.9.23',
  },
  {
    ref: 'Mark 10:14',
    text: 'Suffer the little children to come unto me, and forbid them not: for of such is the kingdom of God.',
    usfm: 'MRK.10.14',
  },
  {
    ref: 'Mark 11:24',
    text: 'What things soever ye desire, when ye pray, believe that ye receive them, and ye shall have them.',
    usfm: 'MRK.11.24',
  },
  {
    ref: 'Luke 1:37',
    text: 'For with God nothing shall be impossible.',
    usfm: 'LUK.1.37',
  },
  {
    ref: 'Luke 6:31',
    text: 'And as ye would that men should do to you, do ye also to them likewise.',
    usfm: 'LUK.6.31',
  },
  {
    ref: 'Luke 11:3',
    text: 'Give us day by day our daily bread.',
    usfm: 'LUK.11.3',
  },
  {
    ref: 'Luke 12:32',
    text: "Fear not, little flock; for it is your Father's good pleasure to give you the kingdom.",
    usfm: 'LUK.12.32',
  },
  {
    ref: 'Luke 16:10',
    text: 'He that is faithful in that which is least is faithful also in much.',
    usfm: 'LUK.16.10',
  },
  {
    ref: 'John 1:1',
    text: 'In the beginning was the Word, and the Word was with God, and the Word was God.',
    usfm: 'JHN.1.1',
  },
  {
    ref: 'John 3:16',
    text: 'For God so loved the world, that he gave his only begotten Son, that whosoever believeth in him should not perish, but have everlasting life.',
    usfm: 'JHN.3.16',
  },
  {
    ref: 'John 6:35',
    text: 'And Jesus said unto them, I am the bread of life: he that cometh to me shall never hunger; and he that believeth on me shall never thirst.',
    usfm: 'JHN.6.35',
  },
  {
    ref: 'John 6:51',
    text: 'I am the living bread which came down from heaven: if any man eat of this bread, he shall live for ever.',
    usfm: 'JHN.6.51',
  },
  {
    ref: 'John 8:12',
    text: 'I am the light of the world: he that followeth me shall not walk in darkness, but shall have the light of life.',
    usfm: 'JHN.8.12',
  },
  {
    ref: 'John 8:32',
    text: 'And ye shall know the truth, and the truth shall make you free.',
    usfm: 'JHN.8.32',
  },
  {
    ref: 'John 10:10',
    text: 'I am come that they might have life, and that they might have it more abundantly.',
    usfm: 'JHN.10.10',
  },
  {
    ref: 'John 11:25',
    text: 'Jesus said unto her, I am the resurrection, and the life: he that believeth in me, though he were dead, yet shall he live.',
    usfm: 'JHN.11.25',
  },
  {
    ref: 'John 13:34',
    text: 'A new commandment I give unto you, That ye love one another; as I have loved you, that ye also love one another.',
    usfm: 'JHN.13.34',
  },
  {
    ref: 'John 14:6',
    text: 'Jesus saith unto him, I am the way, the truth, and the life: no man cometh unto the Father, but by me.',
    usfm: 'JHN.14.6',
  },
  {
    ref: 'John 14:27',
    text: 'Peace I leave with you, my peace I give unto you: not as the world giveth, give I unto you. Let not your heart be troubled, neither let it be afraid.',
    usfm: 'JHN.14.27',
  },
  {
    ref: 'John 15:5',
    text: 'I am the vine, ye are the branches: He that abideth in me, and I in him, the same bringeth forth much fruit: for without me ye can do nothing.',
    usfm: 'JHN.15.5',
  },
  {
    ref: 'John 16:33',
    text: 'In the world ye shall have tribulation: but be of good cheer; I have overcome the world.',
    usfm: 'JHN.16.33',
  },
  {
    ref: 'Acts 16:31',
    text: 'Believe on the Lord Jesus Christ, and thou shalt be saved, and thy house.',
    usfm: 'ACT.16.31',
  },
  {
    ref: 'Romans 5:8',
    text: 'But God commendeth his love toward us, in that, while we were yet sinners, Christ died for us.',
    usfm: 'ROM.5.8',
  },
  {
    ref: 'Romans 8:28',
    text: 'And we know that all things work together for good to them that love God, to them who are the called according to his purpose.',
    usfm: 'ROM.8.28',
  },
  {
    ref: 'Romans 8:31',
    text: 'What shall we then say to these things? If God be for us, who can be against us?',
    usfm: 'ROM.8.31',
  },
  {
    ref: 'Romans 8:38-39',
    text: 'For I am persuaded, that neither death, nor life, nor angels, nor principalities, nor powers, nor things present, nor things to come, nor height, nor depth, nor any other creature, shall be able to separate us from the love of God, which is in Christ Jesus our Lord.',
    usfm: 'ROM.8.38-39',
  },
  {
    ref: 'Romans 10:9',
    text: 'That if thou shalt confess with thy mouth the Lord Jesus, and shalt believe in thine heart that God hath raised him from the dead, thou shalt be saved.',
    usfm: 'ROM.10.9',
  },
  {
    ref: 'Romans 12:2',
    text: 'And be not conformed to this world: but be ye transformed by the renewing of your mind.',
    usfm: 'ROM.12.2',
  },
  {
    ref: 'Romans 12:12',
    text: 'Rejoicing in hope; patient in tribulation; continuing instant in prayer.',
    usfm: 'ROM.12.12',
  },
  {
    ref: 'Romans 15:13',
    text: 'Now the God of hope fill you with all joy and peace in believing, that ye may abound in hope, through the power of the Holy Ghost.',
    usfm: 'ROM.15.13',
  },
  {
    ref: '1 Corinthians 10:31',
    text: 'Whether therefore ye eat, or drink, or whatsoever ye do, do all to the glory of God.',
    usfm: '1CO.10.31',
  },
  {
    ref: '1 Corinthians 13:13',
    text: 'And now abideth faith, hope, charity, these three; but the greatest of these is charity.',
    usfm: '1CO.13.13',
  },
  {
    ref: '1 Corinthians 15:58',
    text: 'Be ye stedfast, unmoveable, always abounding in the work of the Lord, forasmuch as ye know that your labour is not in vain in the Lord.',
    usfm: '1CO.15.58',
  },
  {
    ref: '1 Corinthians 16:14',
    text: 'Let all your things be done with charity.',
    usfm: '1CO.16.14',
  },
  {
    ref: '2 Corinthians 5:7',
    text: 'For we walk by faith, not by sight.',
    usfm: '2CO.5.7',
  },
  {
    ref: '2 Corinthians 5:17',
    text: 'Therefore if any man be in Christ, he is a new creature: old things are passed away; behold, all things are become new.',
    usfm: '2CO.5.17',
  },
  {
    ref: '2 Corinthians 12:9',
    text: 'And he said unto me, My grace is sufficient for thee: for my strength is made perfect in weakness.',
    usfm: '2CO.12.9',
  },
  {
    ref: 'Galatians 5:22-23',
    text: 'But the fruit of the Spirit is love, joy, peace, longsuffering, gentleness, goodness, faith, meekness, temperance: against such there is no law.',
    usfm: 'GAL.5.22-23',
  },
  {
    ref: 'Galatians 6:9',
    text: 'And let us not be weary in well doing: for in due season we shall reap, if we faint not.',
    usfm: 'GAL.6.9',
  },
  {
    ref: 'Ephesians 2:8-9',
    text: 'For by grace are ye saved through faith; and that not of yourselves: it is the gift of God: not of works, lest any man should boast.',
    usfm: 'EPH.2.8-9',
  },
  {
    ref: 'Ephesians 4:32',
    text: "And be ye kind one to another, tenderhearted, forgiving one another, even as God for Christ's sake hath forgiven you.",
    usfm: 'EPH.4.32',
  },
  {
    ref: 'Ephesians 6:10',
    text: 'Finally, my brethren, be strong in the Lord, and in the power of his might.',
    usfm: 'EPH.6.10',
  },
  {
    ref: 'Philippians 1:6',
    text: 'Being confident of this very thing, that he which hath begun a good work in you will perform it until the day of Jesus Christ.',
    usfm: 'PHP.1.6',
  },
  {
    ref: 'Philippians 2:3',
    text: 'Let nothing be done through strife or vainglory; but in lowliness of mind let each esteem other better than themselves.',
    usfm: 'PHP.2.3',
  },
  {
    ref: 'Philippians 4:6-7',
    text: 'Be careful for nothing; but in every thing by prayer and supplication with thanksgiving let your requests be made known unto God. And the peace of God, which passeth all understanding, shall keep your hearts and minds through Christ Jesus.',
    usfm: 'PHP.4.6-7',
  },
  {
    ref: 'Philippians 4:8',
    text: 'Whatsoever things are true, whatsoever things are honest, whatsoever things are just, whatsoever things are pure, whatsoever things are lovely, whatsoever things are of good report; if there be any virtue, and if there be any praise, think on these things.',
    usfm: 'PHP.4.8',
  },
  {
    ref: 'Philippians 4:13',
    text: 'I can do all things through Christ which strengtheneth me.',
    usfm: 'PHP.4.13',
  },
  {
    ref: 'Colossians 3:2',
    text: 'Set your affection on things above, not on things on the earth.',
    usfm: 'COL.3.2',
  },
  {
    ref: 'Colossians 3:15',
    text: 'And let the peace of God rule in your hearts, to the which also ye are called in one body; and be ye thankful.',
    usfm: 'COL.3.15',
  },
  {
    ref: 'Colossians 3:23',
    text: 'And whatsoever ye do, do it heartily, as to the Lord, and not unto men.',
    usfm: 'COL.3.23',
  },
  {
    ref: '1 Thessalonians 5:16-18',
    text: 'Rejoice evermore. Pray without ceasing. In every thing give thanks: for this is the will of God in Christ Jesus concerning you.',
    usfm: '1TH.5.16-18',
  },
  {
    ref: '2 Timothy 1:7',
    text: 'For God hath not given us the spirit of fear; but of power, and of love, and of a sound mind.',
    usfm: '2TI.1.7',
  },
  {
    ref: 'Hebrews 4:16',
    text: 'Let us therefore come boldly unto the throne of grace, that we may obtain mercy, and find grace to help in time of need.',
    usfm: 'HEB.4.16',
  },
  {
    ref: 'Hebrews 10:23',
    text: 'Let us hold fast the profession of our faith without wavering; for he is faithful that promised.',
    usfm: 'HEB.10.23',
  },
  {
    ref: 'Hebrews 11:1',
    text: 'Now faith is the substance of things hoped for, the evidence of things not seen.',
    usfm: 'HEB.11.1',
  },
  {
    ref: 'Hebrews 13:5',
    text: 'Be content with such things as ye have: for he hath said, I will never leave thee, nor forsake thee.',
    usfm: 'HEB.13.5',
  },
  {
    ref: 'Hebrews 13:8',
    text: 'Jesus Christ the same yesterday, and to day, and for ever.',
    usfm: 'HEB.13.8',
  },
  {
    ref: 'James 1:5',
    text: 'If any of you lack wisdom, let him ask of God, that giveth to all men liberally, and upbraideth not; and it shall be given him.',
    usfm: 'JAS.1.5',
  },
  {
    ref: 'James 1:17',
    text: 'Every good gift and every perfect gift is from above, and cometh down from the Father of lights, with whom is no variableness, neither shadow of turning.',
    usfm: 'JAS.1.17',
  },
  {
    ref: 'James 1:19',
    text: 'Let every man be swift to hear, slow to speak, slow to wrath.',
    usfm: 'JAS.1.19',
  },
  {
    ref: 'James 4:8',
    text: 'Draw nigh to God, and he will draw nigh to you.',
    usfm: 'JAS.4.8',
  },
  {
    ref: '1 Peter 4:8',
    text: 'And above all things have fervent charity among yourselves: for charity shall cover the multitude of sins.',
    usfm: '1PE.4.8',
  },
  {
    ref: '1 Peter 5:7',
    text: 'Casting all your care upon him; for he careth for you.',
    usfm: '1PE.5.7',
  },
  {
    ref: '1 John 1:9',
    text: 'If we confess our sins, he is faithful and just to forgive us our sins, and to cleanse us from all unrighteousness.',
    usfm: '1JN.1.9',
  },
  {
    ref: '1 John 3:18',
    text: 'My little children, let us not love in word, neither in tongue; but in deed and in truth.',
    usfm: '1JN.3.18',
  },
  {
    ref: '1 John 4:7',
    text: 'Beloved, let us love one another: for love is of God; and every one that loveth is born of God, and knoweth God.',
    usfm: '1JN.4.7',
  },
  {
    ref: '1 John 4:19',
    text: 'We love him, because he first loved us.',
    usfm: '1JN.4.19',
  },
  {
    ref: 'Revelation 3:20',
    text: 'Behold, I stand at the door, and knock: if any man hear my voice, and open the door, I will come in to him, and will sup with him, and he with me.',
    usfm: 'REV.3.20',
  },
  {
    ref: 'Revelation 21:4',
    text: 'And God shall wipe away all tears from their eyes; and there shall be no more death, neither sorrow, nor crying, neither shall there be any more pain: for the former things are passed away.',
    usfm: 'REV.21.4',
  },
]
