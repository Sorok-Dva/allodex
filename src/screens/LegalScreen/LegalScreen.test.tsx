import { fireEvent, render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '@/lib/i18n';
import { LegalScreen } from './LegalScreen';

describe('LegalScreen', () => {
  it('affiche toutes les sections dans les deux langues et permet le retour', () => {
    const page = render(<I18nProvider initial="fr" storage={null}><LegalScreen /></I18nProvider>);
    expect(page.getByRole('heading', { level: 1 }).textContent).toBe('Conditions générales d’utilisation');
    expect(page.getAllByRole('heading', { level: 2 })).toHaveLength(8);
    fireEvent.click(page.getByRole('button', { name: 'English' }));
    expect(page.getByRole('heading', { level: 1 }).textContent).toBe('Terms of use');
    expect(page.getByRole('heading', { name: '3. Intellectual property' })).toBeTruthy();
    fireEvent.click(page.getByRole('link', { name: 'Back to home' }));
    expect(window.location.pathname).toBe('/');
  });
});
