import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Link, useNavigate } from 'react-router-dom';
import useAuthStore from '../../store/authStore';
import Input from '../../components/common/Input';
import Button from '../../components/common/Button';

const loginSchema = z.object({
  email: z.string().email('Введите корректный email'),
  password: z.string().min(1, 'Введите пароль'),
});

type LoginForm = z.infer<typeof loginSchema>;

const roleRedirects: Record<string, string> = {
  participant: '/dashboard',
  admitter: '/admission',
  scanner: '/scans',
  invigilator: '/invigilator',
  admin: '/admin',
};

const LoginPage: React.FC = () => {
  const { login } = useAuthStore();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (data: LoginForm) => {
    setError(null);
    setLoading(true);
    try {
      await login(data.email, data.password);
      const user = useAuthStore.getState().user;
      const redirect = user ? roleRedirects[user.role] || '/dashboard' : '/dashboard';
      navigate(redirect);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Ошибка входа. Проверьте email и пароль.';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-wrapper">
      <div className="card auth-card">
        <h1>Вход в систему</h1>
        {error && <div className="alert alert-error">{error}</div>}
        <form onSubmit={handleSubmit(onSubmit)}>
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
            placeholder="Введите пароль"
            error={errors.password?.message}
            {...register('password')}
          />
          <Button type="submit" loading={loading} style={{ width: '100%' }}>
            Войти
          </Button>
        </form>
        <p className="text-center mt-16 text-muted">
          Нет аккаунта? <Link to="/register">Зарегистрироваться</Link>
        </p>
      </div>
    </div>
  );
};

export default LoginPage;
