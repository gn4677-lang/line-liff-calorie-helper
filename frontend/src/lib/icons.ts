import {
  Sunrise,
  Sun,
  Moon,
  Coffee,
  Check,
  AlertTriangle,
  Plus,
  Pencil,
  Trash2,
  Navigation,
  Star,
  Zap,
  CalendarCheck,
  UtensilsCrossed,
  TrendingUp,
  LineChart,
  Target,
  ArrowLeft,
  ArrowRight,
  Clock,
  Camera,
  Mic,
  Video,
  Store,
  Loader,
  X,
  Sparkles,
  XCircle
} from 'lucide-react';

export type IconName = keyof typeof ICONS;

export const ICONS = {
  breakfast: Sunrise,
  lunch: Sun,
  dinner: Moon,
  snack: Coffee,
  
  check: Check,
  alertTriangle: AlertTriangle,
  
  add: Plus,
  plus: Plus,
  edit: Pencil,
  delete: Trash2,
  navigate: Navigation,
  favorite: Star,
  quick: Zap,
  
  today: CalendarCheck,
  eat: UtensilsCrossed,
  progress: TrendingUp,
  
  lineChart: LineChart,
  target: Target,
  
  arrowLeft: ArrowLeft,
  arrowRight: ArrowRight,
  clock: Clock,
  camera: Camera,
  mic: Mic,
  video: Video,
  store: Store,
  loader: Loader,
  x: X,
  sparkles: Sparkles,
  xCircle: XCircle
} as const;
