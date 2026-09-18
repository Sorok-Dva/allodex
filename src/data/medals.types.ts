export type MedalRank = {
  completeProgress: number;   // points de progression pour terminer le palier (1 = binaire)
  name: string;
  description: string;
  score: number;              // points de succès gagnés
  reward?: { description: string };
};

export type ConditionItem = { description: string; success: boolean };

export type Medal = {
  id: string;
  name: string;
  description: string;
  icon: string;               // chemin logique de texture (sans extension), ex. "Interface/Icons/Misc/Event/GoldMedal"
  categoryIndex: number;
  subCategoryIndex: number;
  ranks: MedalRank[];         // longueur >= 1
  currentRank: number;        // 0 = aucun palier atteint ; ranks.length = terminé
  progress?: { value: number; title?: string };
  finishDate?: string;        // ISO 8601, présent si terminé
  dressCollection?: (ConditionItem & { slot: string })[];
  medalCollection?: (ConditionItem & { medalId: string })[];
};

export type MedalSubCategory = { name: string };
export type MedalCategory = { name: string; subCategories: MedalSubCategory[] };

export type MedalsDataset = {
  categories: MedalCategory[];
  medals: Medal[];
  totalScore: number;
};

export type MedalFilter = 'all' | 'completed' | 'inProgress';
