import React, { useRef, useState } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Link, useNavigate } from 'react-router-dom';
import useAuthStore from '../../store/authStore';
import api from '../../api/client';
import Input from '../../components/common/Input';
import Button from '../../components/common/Button';
import InstitutionAutocomplete from '../../components/common/InstitutionAutocomplete';

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

const registerSchema = z.object({
  email: z.string().email('Введите корректный email'),
  password: z.string().min(8, 'Пароль должен содержать минимум 8 символов'),
  full_name: z.string().min(1, 'Введите ФИО'),
  school: z.string().min(1, 'Введите название учебного учреждения'),
  institution_location: z.string().optional(),
  is_captain: z.boolean().default(false),
  dob: z.string().optional(),
});

type RegisterForm = z.infer<typeof registerSchema>;

const roleRedirects: Record<string, string> = {
  participant: '/dashboard',
  admitter: '/admission',
  scanner: '/scans',
  invigilator: '/invigilator',
  admin: '/admin',
};

const RegisterPage: React.FC = () => {
  const { register: registerUser } = useAuthStore();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [institutionId, setInstitutionId] = useState<string | undefined>(undefined);

  // Document upload state
  const [documentFile, setDocumentFile] = useState<File | null>(null);
  const [documentError, setDocumentError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
  });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setDocumentError(null);
    if (file && file.size > MAX_FILE_SIZE) {
      setDocumentError('Размер файла не должен превышать 10 МБ');
      setDocumentFile(null);
      return;
    }
    setDocumentFile(file);
  };

  const onSubmit = async (data: RegisterForm) => {
    setError(null);
    setDocumentError(null);

    if (!documentFile) {
      setDocumentError('Необходимо прикрепить скан документа');
      return;
    }

    setLoading(true);
    try {
      // Step 1: Register
      await registerUser({
        email: data.email,
        password: data.password,
        role: 'participant',
        full_name: data.full_name,
        school: data.school,
        institution_id: institutionId,
        institution_location: data.institution_location || undefined,
        is_captain: data.is_captain,
        dob: data.dob || undefined,
      } as never);

      // Step 2: Upload document using the new JWT
      try {
        const formData = new FormData();
        formData.append('file', documentFile);
        await api.post('documents', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
      } catch {
        // Registration succeeded but document upload failed — let user re-upload later
        console.warn('Document upload failed after registration');
      }

      // Step 3: Navigate
      const user = useAuthStore.getState().user;
      const redirect = user ? roleRedirects[user.role] || '/dashboard' : '/dashboard';
      navigate(redirect);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Ошибка регистрации. Попробуйте снова.';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-wrapper">
      <div className="card auth-card">
        <h1>Регистрация</h1>
        {error && <div className="alert alert-error">{error}</div>}
        <form onSubmit={handleSubmit(onSubmit)}>
          <Input
            label="ФИО"
            placeholder="Иванов Иван Иванович"
            error={errors.full_name?.message}
            {...register('full_name')}
          />
          <Input
            label="Email"
            type="email"
            placeholder="example@mail.ru"
            error={errors.email?.message}
            {...register('email')}
          />
          <Input
            label="Пароль"
            type="password"
            placeholder="Минимум 8 символов"
            error={errors.password?.message}
            {...register('password')}
          />
          <div className="form-group">
            <label className="label">Учебное учреждение</label>
            <Controller
              name="school"
              control={control}
              render={({ field }) => (
                <InstitutionAutocomplete
                  value={field.value || ''}
                  onChange={(val, instId) => {
                    field.onChange(val);
                    setInstitutionId(instId);
                  }}
                  placeholder="Начните вводить название..."
                />
              )}
            />
            {errors.school && <span className="error-text">{errors.school.message}</span>}
          </div>
          <Input
            label="Дата рождения"
            type="date"
            error={errors.dob?.message}
            {...register('dob')}
          />
          <Input
            label="Город/филиал учебного учреждения"
            placeholder="Например: Москва, СПб, Казань"
            error={errors.institution_location?.message}
            {...register('institution_location')}
          />
          <div className="form-group">
            <label className="label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input type="checkbox" {...register('is_captain')} />
              Капитан команды
            </label>
          </div>

          {/* Document upload */}
          <div className="form-group">
            <label className="label">Скан документа, удостоверяющего личность *</label>
            <div
              style={{
                border: '2px dashed var(--border-color, #ccc)',
                borderRadius: 8,
                padding: 16,
                textAlign: 'center',
                cursor: 'pointer',
              }}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*,application/pdf"
                onChange={handleFileChange}
                style={{ display: 'none' }}
              />
              {documentFile ? (
                <span>{documentFile.name}</span>
              ) : (
                <span className="text-muted">Нажмите для выбора файла (до 10 МБ)</span>
              )}
            </div>
            {documentError && <span className="error-text">{documentError}</span>}
          </div>

          <Button type="submit" loading={loading} style={{ width: '100%' }}>
            Зарегистрироваться
          </Button>
        </form>
        <p className="text-center mt-16 text-muted">
          Уже есть аккаунт? <Link to="/login">Войти</Link>
        </p>
      </div>
    </div>
  );
};

export default RegisterPage;
