import React, { useState, useEffect } from 'react';
import axios from 'axios';

interface PasswordModalProps {
  unlockApp: () => void;
}

const PasswordModal: React.FC<PasswordModalProps> = ({ unlockApp }) => {
  const [input, setInput] = useState<string>("");
  const [confirmInput, setConfirmInput] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [hashedPassword, setHashedPassword] = useState<string | null>(null);

  useEffect(() => {
    axios.get('/getHashedPassword')
      .then(response => {
        setHashedPassword(response.data.hashedPassword);
      })
      .catch(error => {
        console.error('Error fetching hashed password:', error);
      });
  }, []);

  const handleInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    setInput(e.target.value);
  };

  const handleConfirmInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    setConfirmInput(e.target.value);
  };

  const hashPassword = async (password: string) => {
    const response = await axios.post('/hashPassword', { password });
    return response.data.hashedPassword;
  };

  const handleUnlock = async () => {
    if (hashedPassword === null) {
      if (input === confirmInput) {
        const hashedInput = await hashPassword(input);
        axios.post('/setHashedPassword', { hashedPassword: hashedInput })
          .then(() => {
            setHashedPassword(hashedInput);
            unlockApp();
          })
          .catch(error => {
            console.error('Error saving hashed password:', error);
          });
      } else {
        setError("Passwords do not match!");
      }
    } else {
      const hashedInput = await hashPassword(input);
      if (hashedPassword === hashedInput) {
        unlockApp();
      } else {
        setError("Wrong Password!");
      }
    }
  };

  return (
    <div className="password-modal">
      <input className="password" type="password" placeholder='Password' onChange={handleInput} />
      {!hashedPassword && <input className='password2' type="password" placeholder="Confirm Password" onChange={handleConfirmInput} />}
      <button className="password-button" onClick={handleUnlock}>
        {hashedPassword ? "Unlock" : "Set Password"}
      </button>
      {error && <div className="error-message">{error}</div>}
    </div>
  );
};

export default PasswordModal;
