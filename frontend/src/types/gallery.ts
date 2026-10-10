export interface GalleryProject {
  id: string;
  title: string;
  slug: string;
  short_description?: string;
  description?: string;
  category?: string;
  tags?: string[];
  related_components?: string[];
  cover_image_url?: string;
  project_date?: string;
  featured: boolean;
  published: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
  images?: GalleryImage[];
}

export interface GalleryImage {
  id: string;
  project_id: string;
  image_url: string;
  alt_text?: string;
  sort_order: number;
  created_at: string;
}
