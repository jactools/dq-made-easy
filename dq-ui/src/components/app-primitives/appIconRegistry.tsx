import React from 'react'

export const APP_ICON_NAMES = [
  'arrow-circle-repeat',
  'arrow-curve-left',
  'arrow-curve-right',
  'arrow-left',
  'arrow-right',
  'arrow-up',
  'bell',
  'book',
  'bookmark',
  'box',
  'calendar',
  'chat',
  'check',
  'check-alt',
  'check-circle',
  'chevron-down',
  'chevron-right',
  'chevron-up',
  'clock',
  'close',
  'close-circle',
  'cloud',
  'color',
  'copy',
  'dash-circle-fill',
  'database',
  'document',
  'download',
  'envelope',
  'exclamation-circle',
  'exclamation-triangle',
  'eye-open',
  'filter',
  'folder',
  'globe',
  'hourglass',
  'image-placeholder',
  'info-circle',
  'lightbulb',
  'line-chart',
  'link',
  'list',
  'loading',
  'magnifying-glass',
  'minus',
  'package',
  'padlock-closed',
  'padlock-open',
  'paperclip',
  'pencil',
  'people',
  'person',
  'phone',
  'pie-chart',
  'play',
  'play-circle',
  'plus',
  'power',
  'question-mark',
  'receipt',
  'search',
  'settings',
  'shield-check',
  'sliders',
  'square-arrow-right',
  'table',
  'tag',
  'times',
  'times-circle-fill',
  'trash',
  'truck',
  'user',
  'users',
  'warning',
] as const

export type AppIconName = (typeof APP_ICON_NAMES)[number]

const ARROW_RIGHT = <path d="M5 12h14m-5-5 5 5-5 5" />
const ARROW_LEFT = <path d="M19 12H5m5-5-5 5 5 5" />
const ARROW_UP = <path d="M12 19V5m-5 5 5-5 5 5" />
const ARROW_REPEAT = <><path d="M16 7.5a6 6 0 1 0 1.7 7.4" /><path d="m15.5 6.5 2 1-1 2" /></>
const ARROW_CURVE_LEFT = <><path d="M17 7.5H10.5A4.5 4.5 0 0 0 6 12v2" /><path d="m8.5 11.5-2.5 2.5 2.5 2.5" /></>
const ARROW_CURVE_RIGHT = <><path d="M7 7.5h6.5A4.5 4.5 0 0 1 18 12v2" /><path d="m15.5 11.5 2.5 2.5-2.5 2.5" /></>

const BELL = <><path d="M8 16.5h8l-.8-1.3a5 5 0 0 1-.7-2.6V10a4.5 4.5 0 1 0-9 0v2.6c0 .9-.2 1.8-.7 2.6Z" /><path d="M10.5 18.5a1.5 1.5 0 0 0 3 0" /></>
const BOOK = <><path d="M7 5.5h6.5a3 3 0 0 1 3 3v10H10a3 3 0 0 0-3 3z" /><path d="M10 5.5v13" /></>
const BOOKMARK = <path d="M7.5 5.5h9v13l-4.5-3-4.5 3z" />
const BOX = <><path d="m6.5 8 5.5-3 5.5 3-5.5 3z" /><path d="M6.5 8v8l5.5 3 5.5-3V8" /></>
const CALENDAR = <><rect x="4.5" y="5.5" width="15" height="13" rx="1.75" /><path d="M4.5 9.5h15" /><path d="M8 4.5v3" /><path d="M16 4.5v3" /></>
const CHAT = <path d="M6 7.5h12v7H11l-3.5 3v-3H6z" />
const CHECK = <path d="m8 12 3 3 5-6" />
const CHECK_CIRCLE = <><circle cx="12" cy="12" r="8.5" /><path d="m8.5 12 2.5 2.5L15.8 9.7" /></>
const CHEVRON_DOWN = <path d="M6.5 9.5 12 15l5.5-5.5" />
const CHEVRON_RIGHT = <path d="M9.5 6.5 15 12l-5.5 5.5" />
const CHEVRON_UP = <path d="M6.5 14.5 12 9l5.5 5.5" />
const CLOCK = <><circle cx="12" cy="12" r="8.5" /><path d="M12 8.5v4l2.5 1.5" /></>
const CLOSE = <><path d="M7 7l10 10" /><path d="M17 7 7 17" /></>
const CLOSE_CIRCLE = <><circle cx="12" cy="12" r="8.5" /><path d="M8 8 16 16" /><path d="M16 8 8 16" /></>
const CLOUD = <path d="M7.5 16.5h9a3.5 3.5 0 1 0-.5-7 5 5 0 0 0-9.3 1.5 2.8 2.8 0 0 0 .8 5.5z" />
const COLOR = <path d="M12 4.5c-2.7 3-5 5.3-5 8a5 5 0 0 0 10 0c0-2.7-2.3-5-5-8z" />
const COPY = <><rect x="8" y="8" width="9" height="10" rx="1.5" /><rect x="6" y="6" width="9" height="10" rx="1.5" /></>
const DASH_CIRCLE_FILL = <><circle cx="12" cy="12" r="8.5" /><path d="M8 12h8" /></>
const DATABASE = <><ellipse cx="12" cy="6.5" rx="6.5" ry="2.5" /><path d="M5.5 6.5v5c0 1.4 2.9 2.5 6.5 2.5s6.5-1.1 6.5-2.5v-5" /><path d="M5.5 11.5v5c0 1.4 2.9 2.5 6.5 2.5s6.5-1.1 6.5-2.5v-5" /></>
const DOCUMENT = <><path d="M7.5 5.5h6l3 3v10H7.5z" /><path d="M13.5 5.5v3h3" /></>
const DOWNLOAD = <><path d="M12 5.5v8" /><path d="m8.5 11.5 3.5 3.5 3.5-3.5" /><path d="M6.5 18.5h11" /></>
const ENVELOPE = <><rect x="5" y="7" width="14" height="10" rx="1.75" /><path d="m6 8.5 6 4 6-4" /></>
const EXCLAMATION_CIRCLE = <><circle cx="12" cy="12" r="8.5" /><path d="M12 7.8v5.1" /><path d="M12 15.8h.01" /></>
const WARNING_TRIANGLE = <><path d="M12 5.5 19.5 18H4.5Z" /><path d="M12 10v4.2" /><path d="M12 16.7h.01" /></>
const EYE_OPEN = <><path d="M3.8 12s3-5.5 8.2-5.5 8.2 5.5 8.2 5.5-3 5.5-8.2 5.5S3.8 12 3.8 12Z" /><circle cx="12" cy="12" r="2.3" /></>
const FILTER = <path d="M5.5 6.5h13l-5 6v5l-3 1.5v-6.5z" />
const FOLDER = <path d="M5 8h4.8l1.5 1.5H19v7.5H5z" />
const GLOBE = <><circle cx="12" cy="12" r="8.5" /><path d="M3.5 12h17" /><path d="M12 3.5c2.7 2 4 4.9 4 8.5s-1.3 6.5-4 8.5" /><path d="M12 3.5c-2.7 2-4 4.9-4 8.5s1.3 6.5 4 8.5" /></>
const HOURGLASS = <><path d="M7 5.5h10v2.5c0 1.7-1 3.2-2.6 4.1L12 13l-2.4-.9C7.9 11.2 7 9.7 7 8z" /><path d="M7 18.5h10V16c0-1.7-1-3.2-2.6-4.1L12 13l-2.4-.9C7.9 13.8 7 15.3 7 17z" /></>
const IMAGE_PLACEHOLDER = <><rect x="5" y="6" width="14" height="12" rx="1.75" /><path d="m6.5 15 3.5-3.5 2.5 2.5 2-2 2.5 2.5" /><circle cx="9" cy="9" r="1" /></>
const INFO_CIRCLE = <><circle cx="12" cy="12" r="8.5" /><path d="M12 10.5v5.8" /><path d="M12 7.6h.01" /></>
const LIGHTBULB = <><path d="M9.5 16.5h5" /><path d="M10 15c-1.1-.8-2.5-2.1-2.5-4.2A4.5 4.5 0 0 1 12 6.3a4.5 4.5 0 0 1 4.5 4.5c0 2.1-1.4 3.4-2.5 4.2" /></>
const LINE_CHART = <><path d="M5 17.5h14" /><path d="M6.5 15.5 10 12l2.5 2.5 4.5-6" /></>
const LINK = <><path d="M9 14.5 7.5 16a4 4 0 0 1 0-5.6l2.3-2.3a4 4 0 0 1 5.6 0L17 9" /><path d="M15 9.5 16.5 8a4 4 0 0 1 0 5.6l-2.3 2.3a4 4 0 0 1-5.6 0L7 15" /></>
const LIST = <><path d="M8 7.5h11" /><path d="M8 12h11" /><path d="M8 16.5h11" /><path d="M5 7.5h.01" /><path d="M5 12h.01" /><path d="M5 16.5h.01" /></>
const LOADING = <><path d="M16.8 7.2A8 8 0 1 0 19 12" /><path d="m15.5 6.5 2.5.7-.7 2.5" /></>
const SEARCH = <><circle cx="11" cy="11" r="5.5" /><path d="m15.2 15.2 3.8 3.8" /></>
const SQUARE_ARROW_RIGHT = <><rect x="4.5" y="4.5" width="15" height="15" rx="2" /><path d="M8 12h7" /><path d="m12 8.5 3.5 3.5-3.5 3.5" /></>
const MINUS = <path d="M6.5 12h11" />
const LOCK_CLOSED = <><rect x="6.5" y="10" width="11" height="8" rx="1.75" /><path d="M9 10V8.5a3 3 0 0 1 6 0V10" /></>
const LOCK_OPEN = <><rect x="6.5" y="10" width="11" height="8" rx="1.75" /><path d="M9 10V8.5a3 3 0 0 1 5.5-1.5" /></>
const PAPERCLIP = <><path d="M9.5 8.5 6.5 11.5a4 4 0 1 0 5.7 5.7l5.2-5.2a3 3 0 1 0-4.2-4.2l-5.2 5.2a2 2 0 1 0 2.8 2.8l4.2-4.2" /></>
const PENCIL = <><path d="m6.5 16.5 9.8-9.8 1.9 1.9-9.8 9.8-2.9.5z" /><path d="M13.5 6.5 17.5 10.5" /></>
const PEOPLE = <><path d="M8 12.5a2.5 2.5 0 1 0-2.5-2.5 2.5 2.5 0 0 0 2.5 2.5ZM16 13a2 2 0 1 0-2-2 2 2 0 0 0 2 2Z" /><path d="M4.8 18.5a3.8 3.8 0 0 1 6.4-2.8M13.3 18.5a3.5 3.5 0 0 1 5.9-2.4" /></>
const PHONE = <><rect x="8.5" y="4.5" width="7" height="15" rx="1.8" /><path d="M11 7h2" /><circle cx="12" cy="16.8" r=".6" /></>
const PIE_CHART = <><circle cx="12" cy="12" r="8.5" /><path d="M12 12V4.5A7.5 7.5 0 0 1 19.5 12Z" /></>
const PLAY = <path d="m9 7.5 7 4.5-7 4.5z" />
const PLAY_CIRCLE = <><circle cx="12" cy="12" r="8.5" /><path d="m10 8.5 6 3.5-6 3.5z" /></>
const PLUS = <><path d="M12 6.5v11" /><path d="M6.5 12h11" /></>
const POWER = <><path d="M12 5.5v5" /><circle cx="12" cy="12.5" r="6.5" /></>
const QUESTION_MARK = <><path d="M10.2 9.2a2.5 2.5 0 1 1 4.1 1.9c-.8.6-1.6 1.1-1.8 2.1" /><path d="M12 16.8h.01" /></>
const RECEIPT = <><path d="M7 5.5h10v13l-1.2-.8-1.3.8-1.3-.8-1.2.8-1.2-.8-1.3.8-1.3-.8-1.2.8z" /><path d="M9 9h6M9 12h6" /></>
const SHIELD_CHECK = <><path d="M12 5.5 18 7.5v4.8c0 3.5-2.2 5.8-6 7.7-3.8-1.9-6-4.2-6-7.7V7.5z" /><path d="m9.2 12.2 2 2 3.6-4.2" /></>
const SLIDERS = <><path d="M5.5 8h13" /><path d="M5.5 12h13" /><path d="M5.5 16h13" /><circle cx="9" cy="8" r="1.3" /><circle cx="14.5" cy="12" r="1.3" /><circle cx="10.5" cy="16" r="1.3" /></>
const TABLE = <><rect x="4.5" y="5.5" width="15" height="13" rx="1.75" /><path d="M4.5 10h15" /><path d="M9.5 5.5v13" /><path d="M14.5 5.5v13" /></>
const TAG = <><path d="M5.5 11 11 5.5h7.5v7.5L13 18.5 5.5 11Z" /><circle cx="15.2" cy="8.8" r=".8" /></>
const TRASH = <><path d="M6.5 8.5h11" /><path d="M9 8.5V7a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v1.5" /><path d="M8.5 8.5v9h7v-9" /><path d="M10.5 11v4M13.5 11v4" /></>
const TRUCK = <><path d="M5.5 10h8v5h-8z" /><path d="M13.5 11.5H17l2 2v1.5h-5.5z" /><circle cx="9" cy="17" r="1.5" /><circle cx="16" cy="17" r="1.5" /></>
const USER = <><path d="M12 13a3.5 3.5 0 1 0-3.5-3.5A3.5 3.5 0 0 0 12 13z" /><path d="M6 18.5a6 6 0 0 1 12 0" /></>
const WARNING = <><path d="M12 5.5 19.5 18H4.5Z" /><path d="M12 10v4.2" /><path d="M12 16.7h.01" /></>

const getAppIconShape = (name: AppIconName): React.ReactNode => {
  switch (name) {
    case 'arrow-circle-repeat':
      return ARROW_REPEAT
    case 'arrow-curve-left':
      return ARROW_CURVE_LEFT
    case 'arrow-curve-right':
      return ARROW_CURVE_RIGHT
    case 'arrow-left':
      return ARROW_LEFT
    case 'arrow-right':
      return ARROW_RIGHT
    case 'arrow-up':
      return ARROW_UP
    case 'bell':
      return BELL
    case 'book':
      return BOOK
    case 'bookmark':
      return BOOKMARK
    case 'box':
    case 'package':
      return BOX
    case 'calendar':
      return CALENDAR
    case 'chat':
      return CHAT
    case 'check':
    case 'check-alt':
      return CHECK
    case 'check-circle':
      return CHECK_CIRCLE
    case 'chevron-down':
      return CHEVRON_DOWN
    case 'chevron-right':
      return CHEVRON_RIGHT
    case 'chevron-up':
      return CHEVRON_UP
    case 'clock':
      return CLOCK
    case 'close':
      return CLOSE
    case 'close-circle':
    case 'times-circle-fill':
      return CLOSE_CIRCLE
    case 'cloud':
      return CLOUD
    case 'color':
      return COLOR
    case 'copy':
      return COPY
    case 'dash-circle-fill':
      return DASH_CIRCLE_FILL
    case 'database':
      return DATABASE
    case 'document':
      return DOCUMENT
    case 'download':
      return DOWNLOAD
    case 'envelope':
      return ENVELOPE
    case 'exclamation-circle':
      return EXCLAMATION_CIRCLE
    case 'exclamation-triangle':
    case 'warning':
      return WARNING_TRIANGLE
    case 'eye-open':
      return EYE_OPEN
    case 'filter':
      return FILTER
    case 'folder':
      return FOLDER
    case 'globe':
      return GLOBE
    case 'hourglass':
      return HOURGLASS
    case 'image-placeholder':
      return IMAGE_PLACEHOLDER
    case 'info-circle':
      return INFO_CIRCLE
    case 'lightbulb':
      return LIGHTBULB
    case 'line-chart':
      return LINE_CHART
    case 'link':
      return LINK
    case 'list':
      return LIST
    case 'loading':
      return LOADING
    case 'magnifying-glass':
    case 'search':
      return SEARCH
    case 'settings':
      return SLIDERS
    case 'square-arrow-right':
      return SQUARE_ARROW_RIGHT
    case 'minus':
      return MINUS
    case 'padlock-closed':
      return LOCK_CLOSED
    case 'padlock-open':
      return LOCK_OPEN
    case 'paperclip':
      return PAPERCLIP
    case 'pencil':
      return PENCIL
    case 'people':
    case 'users':
      return PEOPLE
    case 'person':
    case 'user':
      return USER
    case 'phone':
      return PHONE
    case 'pie-chart':
      return PIE_CHART
    case 'play':
      return PLAY
    case 'play-circle':
      return PLAY_CIRCLE
    case 'plus':
      return PLUS
    case 'power':
      return POWER
    case 'question-mark':
      return QUESTION_MARK
    case 'receipt':
      return RECEIPT
    case 'shield-check':
      return SHIELD_CHECK
    case 'sliders':
      return SLIDERS
    case 'table':
      return TABLE
    case 'tag':
      return TAG
    case 'times':
      return CLOSE
    case 'trash':
      return TRASH
    case 'truck':
      return TRUCK
    default:
      return DOCUMENT
  }
}

export const APP_ICON_SHAPES: Record<AppIconName, React.ReactNode> = Object.fromEntries(
  APP_ICON_NAMES.map((name) => [name, getAppIconShape(name)]),
) as Record<AppIconName, React.ReactNode>